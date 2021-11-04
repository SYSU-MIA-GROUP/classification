import torch
import torch.nn as nn
from torchvision import models
from .builder import Networks
# import copy


def _init_weight(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        nn.init.kaiming_normal_(m.weight.data)
    elif classname.find('BatchNorm') != -1 and len(m.weight.shape) > 1:
        nn.init.kaiming_normal_(m.weight.data)
        nn.init.constant_(m.weight.bias)


class Normalization(nn.Module):
    def __init__(self, mean, std, n_channels=3):
        super(Normalization, self).__init__()
        self.n_channels = n_channels
        if mean is None:
            mean = [.0] * n_channels
        if std is None:
            std = [.1] * n_channels
        self.mean = torch.tensor(list(mean)).reshape(
            (1, self.n_channels, 1, 1))
        self.std = torch.tensor(list(std)).reshape((1, self.n_channels, 1, 1))
        self.mean = nn.Parameter(self.mean)
        self.std = nn.Parameter(self.std)

    def forward(self, x):
        y = (x - self.mean / self.std)
        return y


@Networks.register_module('Norm_ResNet18')
class resnet18(nn.Module):
    def __init__(self, n_class, mean=None, std=None, **kwargs):
        super(resnet18, self).__init__()
        self.n_class = n_class

        self.norm = Normalization(mean, std)
        self.encoder = nn.Sequential(
            *list(models.resnet18(pretrained=False).children())[:-1]
            + [nn.Flatten()]
        )
        self.classifier = nn.Linear(
            in_features=512, out_features=n_class, bias=False)
        self.encoder.apply(_init_weight)

    def forward(self, x):
        x_norm = self.norm(x)
        f = self.encoder(x_norm)
        y = self.classifier(f)

        return y


@Networks.register_module('Norm_ResNet18_Small')
class resnet18_small(nn.Module):
    def __init__(self, n_class, mean=None, std=None, **kwargs):
        super(resnet18_small, self).__init__()
        self.n_class = n_class

        self.norm = Normalization(mean, std)
        self.encoder = nn.Sequential(
            *list(models.resnet18(pretrained=False).children())[:-1]
            + [nn.Flatten()]
        )
        self.encoder[0] = nn.Conv2d(3, 64, 3, 1, 1, bias=False)
        self.encoder[3] = nn.Identity()
        self.classifier = nn.Linear(
            in_features=512, out_features=n_class, bias=False)
        self.encoder.apply(_init_weight)

    def forward(self, x):
        x_norm = self.norm(x)
        f = self.encoder(x_norm)
        y = self.classifier(f)

        return y
