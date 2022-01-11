import os
import numpy as np
from torch.utils.data import Dataset
from data_loader.dataset.builder import Datasets
from PIL import Image
# Dataset
@Datasets.register_module("ImageNet_LT")
class LT_Dataset(Dataset):
    
    def __init__(self, root, txt, transform=None, phase='train', imb_type='exp', map_fpath=''):
        self.img_path = []
        self.targets = []
        self.transform = transform
        self.num_classes = 1000
        self.map = np.load(map_fpath)
        with open(txt) as f:
            for line in f:
                self.img_path.append(os.path.join(root, line.split()[0]))
                self.targets.append(self.map[int(line.split()[1])])
        self.num_samples_per_cls = [self.targets.count(i) for i in range(self.num_classes)]
        self.class_weight = self.get_class_weight()
        self.indexes_per_cls = self.get_indexes_per_cls()
        # print(self.num_samples_per_cls)

    def __len__(self):
        return len(self.targets)
        
    def __getitem__(self, index):

        path = self.img_path[index]
        label = self.targets[index]

        with open(path, 'rb') as f:
            sample = Image.open(f).convert('RGB')
        
        if self.transform is not None:
            sample = self.transform(sample)

        return sample, label

    def get_class_list(self):
        return self.class_list

    def get_class_weight(self):
        num_samples_per_cls = np.array(self.num_samples_per_cls)
        num_samples = np.sum(num_samples_per_cls)
        weight = num_samples / (self.num_classes * num_samples_per_cls)
        weight /= np.sum(weight)

        return weight

    def get_indexes_per_cls(self):
        indexes_per_cls = []

        for i in range(self.num_classes):
            indexes = np.where(np.array(self.targets) == i)[0].tolist()
            indexes_per_cls.append(indexes)

        return indexes_per_cls