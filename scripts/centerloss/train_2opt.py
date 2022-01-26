"""trainer script """
import argparse
import os
import random
import warnings
from datetime import datetime

import numpy as np
import torch
import yaml
from base.base_trainer import BaseTrainer
from prefetch_generator import BackgroundGenerator
# from pudb import set_trace
from torch import distributed as dist
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader
from tqdm import tqdm
from utils import AverageMeter, ExpStat


class DataLoaderX(DataLoader):

    def __iter__(self):
        return BackgroundGenerator(super().__iter__())


class Trainer(BaseTrainer):

    def __init__(self, local_rank, config, seed):
        super(Trainer, self).__init__(local_rank, config, seed)

        opt2_config = config['optimizer2']
        self.opt2_name = opt2_config['name']
        self.opt2_params = opt2_config['param']

        scheduler2_config = config['lr_scheduler2']
        self.scheduler2_name = scheduler2_config['name']
        self.scheduler2_params = scheduler2_config['param']

    def train(self):
        #######################################################################
        # Initialize Dataset and Dataloader
        #######################################################################
        train_transform = self.init_transform(self.train_transform_name,
                                              **self.train_transform_params)
        trainset = self.init_dataset(self.trainset_name,
                                     transform=train_transform,
                                     **self.trainset_params)
        train_sampler = self.init_sampler(self.train_sampler_name,
                                          dataset=trainset,
                                          **self.trainloader_params)
        self.trainloader = DataLoaderX(trainset,
                                       batch_size=self.train_batchsize,
                                       shuffle=(train_sampler is None),
                                       num_workers=self.train_workers,
                                       pin_memory=True,
                                       drop_last=True,
                                       sampler=train_sampler)

        val_transform = self.init_transform(self.val_transform_name,
                                            **self.val_transform_params)
        valset = self.init_dataset(self.valset_name,
                                   transform=val_transform,
                                   **self.valset_params)
        val_sampler = self.init_sampler(self.val_sampler_name,
                                        dataset=valset,
                                        **self.trainloader_params)
        self.valloader = DataLoaderX(valset,
                                     batch_size=self.val_batchsize,
                                     shuffle=(val_sampler is None),
                                     num_workers=self.val_workers,
                                     pin_memory=True,
                                     drop_last=False,
                                     sampler=val_sampler)

        if self.local_rank != -1:
            dist.barrier()

            if not self.train_sampler_name:
                self.train_sampler_name = "DistributedSampler"

            if not self.val_sampler_name:
                self.val_sampler_name = "DistributedSampler"

            self.log(f"world_size={self.world_size}, "
                     f"local_rank={self.local_rank}, "
                     f"train_sampler='{self.train_sampler_name}', "
                     f"val_sampler='{self.val_sampler_name}'")

        #######################################################################
        # Initialize Network
        #######################################################################
        self.model = self.init_model(self.network_name,
                                     num_classes=trainset.num_classes,
                                     **self.network_params)

        #######################################################################
        # Initialize DistributedDataParallel
        #######################################################################

        if self.local_rank != -1:
            self.model = DistributedDataParallel(self.model,
                                                 device_ids=[self.local_rank],
                                                 output_device=self.local_rank)

        #######################################################################
        # Initialize Loss
        #######################################################################
        weight = self.get_class_weight(trainset.num_samples_per_cls,
                                       **self.loss_params)  # 包含weight_type
        self.criterion = self.init_loss(self.loss_name,
                                        weight=weight,
                                        **self.loss_params)

        #######################################################################
        # Initialize Optimizer
        #######################################################################
        self.optimizer = self.init_optimizer(self.opt_name,
                                             self.model.parameters(),
                                             **self.opt_params)
        self.optimizer2 = self.init_optimizer(self.opt2_name,
                                              self.criterion.parameters(),
                                              **self.opt2_params)

        #######################################################################
        # Initialize LR Scheduler
        #######################################################################
        self.lr_scheduler = self.init_lr_scheduler(self.scheduler_name,
                                                   self.optimizer,
                                                   **self.scheduler_params)
        self.lr_scheduler2 = self.init_lr_scheduler(self.scheduler2_name,
                                                    self.optimizer2,
                                                    **self.scheduler2_params)

        #######################################################################
        # Start Training
        #######################################################################

        if self.local_rank in [-1, 0]:
            best_mr = 0.
            best_epoch = 1
            best_group_mr = []
            # average of mean recall in the last several epochs(default: 5)
            last_mrs = []  # General: include all classes.
            last_maj_mrs = []  # Majority classes: > 100 images
            last_med_mrs = []  # Medium classes: 20 ~ 100 images
            last_min_mrs = []  # Minority classes: < 20 images
            start_time = datetime.now()

        self.final_epoch = self.start_epoch + self.total_epochs

        for cur_epoch in range(self.start_epoch, self.final_epoch):
            self.lr_scheduler.step()
            self.lr_scheduler2.step()

            if self.local_rank != -1:
                dist.barrier()
                train_sampler.set_epoch(cur_epoch)
                val_sampler.set_epoch(cur_epoch)

            train_stat, train_loss = self.train_epoch(
                cur_epoch=cur_epoch,
                trainloader=self.trainloader,
                model=self.model,
                criterion=self.criterion,
                optimizer=self.optimizer,
                optimizer2=self.optimizer2,
                dataset=trainset,
            )

            val_stat, val_loss = self.evaluate(
                cur_epoch=cur_epoch,
                valloader=self.valloader,
                model=self.model,
                criterion=self.criterion,
                dataset=trainset,
            )

            if self.local_rank in [-1, 0]:

                if self.final_epoch - cur_epoch <= 5:
                    last_mrs.append(val_stat.mr)
                    last_maj_mrs.append(val_stat.group_mr[0])
                    last_med_mrs.append(val_stat.group_mr[1])
                    last_min_mrs.append(val_stat.group_mr[2])

                self.log(
                    f"Epoch[{cur_epoch:>3d}/{self.final_epoch-1}] "
                    f"Trainset Total Loss={train_loss['total']:.1f} "
                    f"MR={train_stat.mr:>7.2%}"
                    f"[{train_stat.group_mr[0]:>7.2%}, "
                    f"{train_stat.group_mr[1]:>7.2%}, "
                    f"{train_stat.group_mr[2]:>7.2%}]"
                    f" || "
                    f"Valset Loss={val_loss:>4.2f} "
                    f"MR={val_stat.mr:>7.2%} "
                    f"[{val_stat.group_mr[0]:>7.2%}, "
                    f"{val_stat.group_mr[1]:>7.2%}, "
                    f"{val_stat.group_mr[2]:>7.2%}]",
                    log_level='file')

                # Save log by tensorboard
                self.writer.add_scalar(f"{self.exp_name}/LR",
                                       self.optimizer.param_groups[-1]["lr"],
                                       cur_epoch)
                self.writer.add_scalars(f"{self.exp_name}/Loss", {
                    "train_loss": train_loss,
                    "val_loss": val_loss
                }, cur_epoch)
                self.writer.add_scalars(f"{self.exp_name}/Recall", {
                    "train_mr": train_stat.mr,
                    "val_mr": val_stat.mr
                }, cur_epoch)
                self.writer.add_scalars(
                    f"{self.exp_name}/TrainGroupRecall", {
                        "maj_mr": train_stat.group_mr[0],
                        "med_mr": train_stat.group_mr[1],
                        "min_mr": train_stat.group_mr[2]
                    }, cur_epoch)
                self.writer.add_scalars(
                    f"{self.exp_name}/ValGroupRecall", {
                        "maj_mr": val_stat.group_mr[0],
                        "med_mr": val_stat.group_mr[1],
                        "min_mr": val_stat.group_mr[2]
                    }, cur_epoch)

                is_best = val_stat.mr > best_mr

                if is_best:
                    best_mr = val_stat.mr
                    best_epoch = cur_epoch
                    best_group_mr = val_stat.group_mr

                if (not cur_epoch % self.save_period) or is_best:
                    self.save_checkpoint(epoch=cur_epoch,
                                         model=self.model,
                                         optimizer=self.optimizer,
                                         is_best=is_best,
                                         mr=val_stat.mr,
                                         group_mr=val_stat.group_mr,
                                         prefix=f"seed{self.seed}",
                                         save_dir=self.exp_dir)

        if self.local_rank in [-1, 0]:
            end_time = datetime.now()
            dur_time = str(end_time - start_time)[:-7]  # 取到秒

            final_mr = np.around(np.mean(last_mrs), decimals=4)
            final_maj_mr = np.around(np.mean(last_maj_mrs), decimals=4)
            final_med_mr = np.around(np.mean(last_med_mrs), decimals=4)
            final_min_mr = np.around(np.mean(last_min_mrs), decimals=4)

            self.log(
                f"\n===> Total Runtime: {dur_time}\n\n"
                f"===> Best mean recall:  (epoch{best_epoch}) {best_mr:>7.2%} "
                f"[{best_group_mr[0]:>7.2%}, "
                f"{best_group_mr[1]:>7.2%}, "
                f"{best_group_mr[2]:>7.2%}]\n\n"
                f"===> Last mean recall: {val_stat.mr:>6.2%} "
                f"[{val_stat.group_mr[0]:>7.2%}, "
                f"{val_stat.group_mr[1]:>7.2%}, "
                f"{val_stat.group_mr[2]:>7.2%}]\n\n"
                f"===> Final average mean recall of last 5 epochs: "
                f"{final_mr:>6.2%} "
                f"[{final_maj_mr:>7.2%}, "
                f"{final_med_mr:>7.2%}, "
                f"{final_min_mr:>7.2%}]\n\n"
                f"===> Save directory: '{self.exp_dir}'\n"
                f"*********************************************************"
                f"*********************************************************\n")

    def train_epoch(self, cur_epoch, trainloader, model, criterion, optimizer,
                    optimizer2, dataset, **kwargs):

        model.train()
        criterion.train()

        if self.local_rank in [-1, 0]:
            train_pbar = tqdm(
                total=len(trainloader),
                desc=f"Train Epoch[{cur_epoch:>3d}/{self.final_epoch-1}]")

        train_loss_meter = AverageMeter()
        train_stat = ExpStat(dataset)

        for i, (batch_imgs, batch_labels) in enumerate(trainloader):
            batch_imgs = batch_imgs.cuda()
            batch_labels = batch_labels.cuda()
            batch_probs = model(batch_imgs)
            avg_loss = criterion(batch_probs, batch_labels)

            optimizer.zero_grad()
            optimizer2.zero_grad()
            avg_loss.backward()
            optimizer2.step()
            optimizer.step()

            if self.local_rank != -1:
                dist.barrier()
                avg_loss = self._reduce_tensor(avg_loss)

            batch_preds = torch.argmax(batch_probs, dim=1)
            # batch_preds = train_stat.get_preds_by_eudist(
            #     batch_vecs, criterion.centers.detach())
            train_loss_meter.update(avg_loss.item(), 1)
            train_stat.update(batch_labels, batch_preds)

            if self.local_rank in [-1, 0]:
                train_pbar.update()
                train_pbar.set_postfix_str(
                    f"LR:[{optimizer.param_groups[0]['lr']:.1e}, "
                    f"{optimizer2.param_groups[0]['lr']:.1e}] "
                    f"Loss: {train_loss_meter.avg:4.2f} ")

        if self.local_rank != -1:
            dist.barrier()
            train_stat._cm = self._reduce_tensor(train_stat._cm, op='sum')

        if self.local_rank in [-1, 0]:
            train_pbar.set_postfix_str(
                f"LR:[{optimizer.param_groups[0]['lr']:.1e}, "
                f"{optimizer2.param_groups[0]['lr']:.1e}] "
                f"Loss:{train_loss_meter.avg:>4.2f} "
                f"MR:{train_stat.mr:>7.2%} "
                f"[{train_stat.group_mr[0]:>3.0%}, "
                f"{train_stat.group_mr[1]:>3.0%}, "
                f"{train_stat.group_mr[2]:>3.0%}]")

            train_pbar.close()

        return train_stat, train_loss_meter.avg

    def evaluate(self, cur_epoch, valloader, model, criterion, dataset,
                 **kwargs):
        model.eval()
        criterion.eval()

        if self.local_rank in [-1, 0]:
            val_pbar = tqdm(total=len(valloader),
                            ncols=0,
                            desc="                 Val")

        val_loss_meter = AverageMeter()
        val_stat = ExpStat(dataset)
        with torch.no_grad():
            for i, (batch_imgs, batch_labels) in enumerate(valloader):
                batch_imgs = batch_imgs.cuda(non_blocking=True)
                batch_labels = batch_labels.cuda(non_blocking=True)

                batch_probs = model(batch_imgs, out='mlp')
                batch_preds = torch.argmax(batch_probs, dim=1)
                avg_loss = criterion(batch_probs, batch_labels)
                # batch_vecs = model(batch_imgs, out='vec')
                # batch_preds = val_stat.get_preds_by_eudist(
                #     batch_vecs, criterion.centers.detach())
                # avg_loss = criterion(batch_vecs, batch_labels)

                if self.local_rank != -1:
                    dist.barrier()
                    avg_loss = self._reduce_tensor(avg_loss)

                val_loss_meter.update(avg_loss.item(), 1)
                val_stat.update(batch_labels, batch_preds)

                if self.local_rank in [-1, 0]:
                    val_pbar.update()
                    val_pbar.set_postfix_str(
                        f"Loss:{val_loss_meter.avg:>3.1f}")

        if self.local_rank != -1:
            # all reduce the statistical confusion matrix
            dist.barrier()
            val_stat._cm = self._reduce_tensor(val_stat._cm, op='sum')

        if self.local_rank in [-1, 0]:
            val_pbar.set_postfix_str(f"Loss:{val_loss_meter.avg:>4.2f} "
                                     f"MR:{val_stat.mr:>7.2%} "
                                     f"[{val_stat.group_mr[0]:>3.0%}, "
                                     f"{val_stat.group_mr[1]:>3.0%}, "
                                     f"{val_stat.group_mr[2]:>3.0%}]")
            val_pbar.close()

        return val_stat, val_loss_meter.avg


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local_rank",
                        type=int,
                        default=-1,
                        help="Local Rank for distributed training. "
                        "if single-GPU, default: -1")
    parser.add_argument("--config_path", type=str, help="path of config file")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    return args


def _set_random_seed(seed=0, cuda_deterministic=False):
    """Set seed and control the balance between reproducity and efficiency

    Reproducity: cuda_deterministic = True
    Efficiency: cuda_deterministic = False
    """

    random.seed(seed)
    np.random.seed(seed)

    assert torch.cuda.is_available()
    torch.manual_seed(seed)  # sets the seed for generating random numbers.
    torch.cuda.manual_seed_all(seed)

    if cuda_deterministic:  # slower, but more reproducible
        torch.backends.cudnn.enabled = False
        torch.backends.cudnn.deterministic = True  # 固定内部随机性
        torch.backends.cudnn.benchmark = False
    else:
        torch.backends.cudnn.enabled = True
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = True  # 输入尺寸一致，加速训练


def main(args):
    warnings.filterwarnings("ignore")
    _set_random_seed(seed=args.seed)
    with open(args.config_path, "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    trainer = Trainer(local_rank=args.local_rank,
                      config=config,
                      seed=args.seed)
    trainer.train()


if __name__ == "__main__":
    args = parse_args()

    if "LOCAL_RANK" in os.environ:
        args.local_rank = int(os.environ["LOCAL_RANK"])

    main(args)