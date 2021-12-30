"""Base Trainer"""
# ############# Build-in Package #############
# import math
import abc
# import shutil
import logging
import os
from os.path import join

# ########### Third-Party Package ############
import numpy as np
import torch
# ############## Custom package ##############
from data_loader.dataset.builder import Datasets
from data_loader.sampler.builder import Samplers
from data_loader.transform.builder import Transforms
from model.loss.builder import Losses
from model.module.builder import Modules
from model.network.builder import Networks
# from pudb import set_trace
from torch import distributed as dist
from torch.utils.data.distributed import DistributedSampler
from torch.utils.tensorboard import SummaryWriter
from utils import GradualWarmupScheduler


class BaseTrainer:
    def __init__(self, local_rank=-1, config=None):
        """ Base trainer for all experiments.  """

        #######################################################################
        # Device setting
        #######################################################################
        assert torch.cuda.is_available()
        torch.backends.cudnn.enable = True
        torch.backends.cudnn.benchmark = True

        self.local_rank = local_rank
        if self.local_rank != -1:
            dist.init_process_group(backend="nccl")
            torch.cuda.set_device(self.local_rank)
            self.global_rank = dist.get_rank()
            self.world_size = dist.get_world_size()

        #######################################################################
        # Experiment setting
        #######################################################################
        self.exp_config = config["experiment"]
        self.exp_name = self.exp_config["name"]
        self.user_root = os.environ["HOME"]
        self.exp_root = join(self.user_root, "Experiments")
        self.start_epoch = self.exp_config["start_epoch"]
        self.total_epochs = self.exp_config["total_epochs"]

        self._set_configs(config)  # set common configs
        self.resume = self.exp_config["resume"]
        if self.resume:
            if "/" in self.exp_config["resume_fpath"]:
                self.resume_fpath = self.exp_config["resume_fpath"]
            else:
                self.resume_fpath = join(self.exp_root, self.exp_name,
                                         self.exp_config["resume_fpath"])
            self.checkpoint, resume_log =\
                self.resume_checkpoint(self.resume_fpath)
            self.start_epoch = self.checkpoint["epoch"] + 1

        if self.local_rank in [-1, 0]:
            self.eval_period = self.exp_config["eval_period"]

            # directory to save experiment result
            self.save_period = self.exp_config["save_period"]
            self.exp_dir = join(self.exp_root, self.exp_name)
            os.makedirs(self.exp_dir, exist_ok=True)

            # directory to save tensorboard record
            self.tb_dir = join(self.exp_root, "Tensorboard", self.exp_name)
            os.makedirs(self.tb_dir, exist_ok=True)
            self.writer = SummaryWriter(log_dir=self.tb_dir)

            # path to save logging record
            self.log_fpath = join(self.exp_dir, self.exp_config["log_fname"])
            self.logger = self.init_logger(self.log_fpath)

            exp_init_log = f"\n****************************************"\
                f"****************************************************"\
                f"\nExperiment: {self.exp_name}\n"\
                f"Start_epoch: {self.start_epoch}\n"\
                f"Total_epochs: {self.total_epochs}\n"\
                f"Save dir: {self.exp_dir}\n"\
                f"Tensorboard dir: {self.tb_dir}\n"\
                f"Save peroid: {self.save_period}\n"\
                f"Resume Training: {self.resume}\n"\
                f"Distributed Training: "\
                f"{True if self.local_rank != -1 else False}\n"\
                f"**********************************************"\
                f"**********************************************\n"

            self.log(exp_init_log)
            if self.resume:
                self.log(resume_log)

    def _set_configs(self, config):
        #######################################################################
        # Dataset setting
        #######################################################################
        train_transform_config = config["train_transform"]
        self.train_transform_name = train_transform_config["name"]
        self.train_transform_params = train_transform_config["param"]

        trainset_config = config["train_dataset"]
        self.trainset_name = trainset_config["name"]
        self.trainset_params = trainset_config["param"]

        val_transform_config = config["val_transform"]
        self.val_transform_name = val_transform_config["name"]
        self.val_transform_params = val_transform_config["param"]

        valset_config = config["val_dataset"]
        self.valset_name = valset_config["name"]
        self.valset_params = valset_config["param"]

        #######################################################################
        # Dataloader setting
        #######################################################################
        self.trainloader_params = config["trainloader"]
        self.train_batchsize = self.trainloader_params["batch_size"]
        self.train_workers = self.trainloader_params["num_workers"]
        self.train_sampler_name = self.trainloader_params["sampler"]

        self.valloader_params = config["valloader"]
        self.val_batchsize = self.valloader_params["batch_size"]
        self.val_workers = self.valloader_params["num_workers"]

        #######################################################################
        # Network setting
        #######################################################################
        network_config = config["network"]
        self.network_name = network_config["name"]
        self.network_params = network_config["param"]

        #######################################################################
        # Loss setting
        #######################################################################
        loss_config = config["loss"]
        self.loss_name = loss_config["name"]
        self.loss_params = loss_config["param"]

        #######################################################################
        # Optimizer setting
        #######################################################################
        opt_config = config["optimizer"]
        self.opt_name = opt_config["name"]
        self.opt_params = opt_config["param"]

        #######################################################################
        # LR scheduler setting
        #######################################################################
        scheduler_config = config["lr_scheduler"]
        self.scheduler_name = scheduler_config["name"]
        self.scheduler_params = scheduler_config["param"]

    def init_transform(self, transform_name, **kwargs):
        log_level = kwargs.get("log_level", "default")
        kwargs.pop("log_level", None)

        transform = Transforms.get(transform_name)(**kwargs)
        transform_init_log = f"===> Initialized {transform_name}: {kwargs}"
        self.log(transform_init_log, log_level)
        return transform

    def init_dataset(self, dataset_name, **kwargs):
        log_level = kwargs.pop("log_level", "default")
        kwargs["data_root"] = join(self.user_root, "Data", kwargs["data_root"])

        dataset = Datasets.get(dataset_name)(**kwargs)

        dataset_init_log = f"===> Initialized {kwargs['phase']} "\
            f"{dataset_name}: size={len(dataset)}, "\
            f"classes={dataset.num_classes}\n"\
            f"imgs_per_cls={dataset.num_samples_per_cls}"
        self.log(dataset_init_log, log_level)
        return dataset

    def init_sampler(self, sampler_name, **kwargs):
        log_level = kwargs.pop("log_level", "default")

        if sampler_name in {None, "None", ""}:
            sampler = None
            sampler_init_log = "===> Use Default Sampler"
        elif sampler_name == "DistributedSampler":
            sampler = DistributedSampler(kwargs["dataset"])
            sampler_init_log = "===> Initialized DistributedSampler"
        else:
            sampler = Samplers.get(sampler_name)(**kwargs)
            sampler_init_log = f"===> Initialized {sampler_name} with"\
                f" resampled size={len(sampler)}"
        self.log(sampler_init_log, log_level)
        return sampler

    def init_model(self,
                   network_name,
                   resume=False,
                   checkpoint=None,
                   **kwargs):
        log_level = kwargs.pop("log_level", "default")

        model = Networks.get(network_name)(**kwargs)
        total_params = self.count_model_params(model)
        model.cuda()

        prefix = "Initialized"
        if resume:
            model = self.update_state_dict(model, checkpoint["model"])
            prefix = "Resumed checkpoint model_params to"
        elif kwargs.get("pretrained", False):
            state_dict = torch.load(kwargs["pretrained_fpath"],
                                    map_location="cpu")
            model = self.update_state_dict(model, state_dict)
            prefix = "Resumed pretrained model_params to"

        kwargs.pop("checkpoint", None)
        model_init_log = f"===> {prefix} {network_name}(total_params"\
            f"={total_params:.2f}m): {kwargs}"
        self.log(model_init_log, log_level)
        return model

    def freeze_model(self, model, unfreeze_keys=["fc"]):
        """Freeze model parameters except some given keys
        Default: leave fc unfreezed
        """
        self.log(f"===> Freeze model except for keys{unfreeze_keys}")
        for named_key, var in model.named_parameters():
            if unfreeze_keys is None:
                var.requires_grad = False
            else:
                if any(key in named_key for key in unfreeze_keys):
                    var.requires_grad = True
                else:
                    var.requires_grad = False

    def get_class_weight(self, num_samples_per_cls, weight_type, **kwargs):
        num_samples_per_cls = torch.FloatTensor(num_samples_per_cls)
        if weight_type == "inverse":
            num_samples = torch.sum(num_samples_per_cls)
            num_classes = len(num_samples_per_cls)
            weight = num_samples / (num_classes * num_samples_per_cls)
            weight /= torch.sum(weight)
        elif weight_type == "proportion":
            num_samples = torch.sum(num_samples_per_cls)
            weight = num_samples_per_cls / num_samples
            weight /= torch.sum(weight)
        elif weight_type == "Class-balanced":
            beta = kwargs["beta"]
            weight = (1.0 - beta) / \
                (1.0 - torch.pow(beta, num_samples_per_cls))
            weight /= torch.sum(weight)
        else:
            weight = None
        return weight

    def init_loss(self, loss_name, **kwargs):
        log_level = kwargs.pop("log_level", "default")

        weight = kwargs.get('weight', None)
        if weight is not None:
            display_weight = weight.numpy().round(2)
            self.log(f"===> Computed class_weight:\n{display_weight}")

        loss = Losses.get(loss_name)(**kwargs)

        kwargs.pop("weight")
        self.log(f"===> Initialized {loss_name}: {kwargs}", log_level)
        return loss.cuda()

    def init_optimizer(self, opt_name, model_params, **kwargs):
        # model_params = [
        #     {"model_params": [p for n, p in self.model.named_parameters()
        #                    if not any(nd in n for nd in ["bias", "bn"])],
        #      "weight_decay": self.weight_decay},
        #     {"model_params": [p for n, p in self.model.named_parameters()
        #                    if any(nd in n for nd in ["bias", "bn"])],
        #      "weight_decay": 0.0}]
        log_level = kwargs.pop("log_level", "default")

        optimizer = getattr(torch.optim, opt_name)(model_params, **kwargs)
        prefix = "Initialized"
        if kwargs.get("resume", False):
            checkpoint = kwargs.pop("checkpoint", None)
            optimizer = self.update_state_dict(
                optimizer, checkpoint["optimizer"])
            prefix = "Resumed"

        self.log(f"===> {prefix} {opt_name}: {kwargs}", log_level)
        return optimizer

    def init_lr_scheduler(self, scheduler_name, optimizer, **kwargs):
        warmup_epochs = kwargs.pop("warmup_epochs", 5)

        lr_scheduler = getattr(torch.optim.lr_scheduler,
                               scheduler_name)(optimizer, **kwargs)
        self.log(f"===> Initialized {scheduler_name}: {kwargs}")
        if warmup_epochs > 0:
            lr_scheduler = GradualWarmupScheduler(
                optimizer,
                multiplier=1,
                warmup_epochs=warmup_epochs,
                after_scheduler=lr_scheduler,
            )
            self.log(f"===> Initialized gradual warmup scheduler: "
                     f"warmup_epochs={warmup_epochs}")
        return lr_scheduler

    def init_module(self, module_name, **kwargs):
        module = Modules.get(module_name)(**kwargs)
        del kwargs["model"]
        self.log(f"===> Initialized {module_name}: {kwargs}")
        return module

    def _reduce_loss(self, tensor):
        with torch.no_grad():
            dist.reduce(tensor, dst=0)
            if not self.local_rank:
                tensor /= self.world_size

    def resume_checkpoint(self, resume_fpath):
        checkpoint = torch.load(resume_fpath, map_location="cpu")
        mr = checkpoint["mr"]
        recalls = checkpoint.get("group_recalls", "-")

        resume_log = f"===> Resume checkpoint from '{resume_fpath}'.\n"\
            f"Mean recall:{mr:.2%}\nGroup recalls:{recalls}\n"
        return checkpoint, resume_log

    def save_checkpoint(self, epoch, model, optimizer, is_best, mr, group_mr,
                        save_dir, prefix=None, criterion=None):
        checkpoint = {"model": model.state_dict()
                      if self.local_rank == -1 else model.module.state_dict(),
                      "optimizer": optimizer.state_dict(),
                      "criterion": criterion.state_dict()
                      if criterion is not None else None,
                      "best": is_best,
                      "epoch": epoch,
                      "mr": mr,
                      "group_mr": group_mr}
        save_fname = "best.pth.tar" if is_best else "last.pth.tar"
        if prefix is not None:
            save_fname = prefix + "_" + save_fname
        save_path = join(save_dir, save_fname)
        torch.save(checkpoint, save_path)

    def init_logger(self, log_fpath):
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        # Save log to file
        file_handler = logging.FileHandler(log_fpath, mode="a")
        file_handler.setLevel(logging.DEBUG)
        file_handler_formatter = logging.Formatter(
            "%(asctime)s: %(levelname)s:"
            " [%(filename)s:%(lineno)d]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_handler_formatter)

        # print to the screen
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        # stream_handler.setFormatter(formatter)

        # add two handler to the logger
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

        return logger

    def log(self, log, log_level="default"):
        if self.local_rank in [-1, 0]:
            if log_level == "default":
                # both stram and file
                self.logger.info(log)
            elif log_level == "stream":
                print(log)
            elif log_level == "file":
                self.logger.debug(log)

    def count_model_params(self, model):
        total_params = 0.
        for x in filter(lambda p: p.requires_grad, model.parameters()):
            total_params += np.prod(x.data.numpy().shape)
        total_params /= 10**6
        return total_params

    def update_state_dict(self, module, checkpoint_state_dict):
        """Only update state dict that the module needs and print those
        unupdated keys of the module"""
        module_state_dict = module.state_dict()
        update_items = {
            key: value
            for key, value in checkpoint_state_dict.items()
            if key in module_state_dict.keys()
        }
        unupdated_keys = [
            key for key in module_state_dict.keys()
            if key not in update_items.keys()
        ]
        self.log(f"Found unused keys from checkpoint: {unupdated_keys}")
        module_state_dict.update(update_items)
        module.load_state_dict(module_state_dict)
        return module

    @abc.abstractmethod
    def train(self):
        raise NotImplementedError

    @abc.abstractmethod
    def train_epoch(self, epoch):
        raise NotImplementedError

    @abc.abstractmethod
    def evaluate(self, epoch):
        raise NotImplementedError
