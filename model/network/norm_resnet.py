import torch
import torch.nn as nn
# from torchvision import models
from .builder import Networks


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


def conv3x3(in_planes: int, out_planes: int, stride: int = 1,
            groups: int = 1, dilation: int = 1) -> nn.Conv2d:
    """3x3 convolution with padding"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=3,
                     stride=stride, padding=dilation, groups=groups,
                     bias=False, dilation=dilation)


def conv1x1(in_planes: int, out_planes: int, stride: int = 1) -> nn.Conv2d:
    """1x1 convolution"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=1,
                     stride=stride, bias=False)


class BasicBlock(nn.Module):
    expansion: int = 1

    def __init__(self, inplanes, planes, stride=1, downsample=None, groups=1,
                 base_width=64, dilation=1, norm_layer=None):
        super(BasicBlock, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        if groups != 1 or base_width != 64:
            raise ValueError(
                'BasicBlock only supports groups=1 and base_width=64')
        if dilation > 1:
            raise NotImplementedError(
                "Dilation > 1 not supported in BasicBlock")
        # Both self.conv1 and self.downsample layers
        # downsample the input when stride != 1
        self.conv1 = conv3x3(inplanes, planes, stride)
        self.bn1_adv = norm_layer(planes)
        self.bn1_clean = norm_layer(planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3(planes, planes)
        self.bn2_adv = norm_layer(planes)
        self.bn2_clean = norm_layer(planes)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x, is_adv=False):
        identity = x

        out = self.conv1(x)
        out = self.bn1_adv(out) if is_adv else self.bn1_clean(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2_adv(out) if is_adv else self.bn2_clean(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity
        out = self.relu(out)

        return out


class Bottleneck(nn.Module):
    # Bottleneck in torchvision places the stride for downsampling at
    # 3x3 convolution(self.conv2). while original implementation places
    # the stride at the first 1x1 convolution(self.conv1)
    # according to "Deep residual learning for image recognition"
    # https://arxiv.org/abs/1512.03385.
    # This variant is also known as ResNet V1.5 and improves accuracy
    # according to:
    # https://ngc.nvidia.com/catalog/model-scripts/nvidia:resnet_50_v1_5_for_pytorch.

    expansion: int = 4

    def __init__(self, inplanes, planes, stride=1, downsample=None, groups=1,
                 base_width=64, dilation=1, norm_layer=None):
        super(Bottleneck, self).__init__()
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        width = int(planes * (base_width / 64.)) * groups
        # Both self.conv2 and self.downsample layers
        # downsample the input when stride != 1
        self.conv1 = conv1x1(inplanes, width)
        self.bn1_adv = norm_layer(planes)
        self.bn1_clean = norm_layer(planes)
        self.conv2 = conv3x3(width, width, stride, groups, dilation)
        self.bn2_adv = norm_layer(planes)
        self.bn2_clean = norm_layer(planes)
        self.conv3 = conv1x1(width, planes * self.expansion)
        self.bn3_adv = norm_layer(planes * self.expansion)
        self.bn3_clean = norm_layer(planes * self.expansion)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x, is_adv=False):
        identity = x

        out = self.conv1(x)
        out = self.bn1_adv(out) if is_adv else self.bn1_clean(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2_adv(out) if is_adv else self.bn2_clean(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3_adv(out) if is_adv else self.bn3_clean(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out += identity
        out = self.relu(out)

        return out


class NormResNet(nn.Module):
    def __init__(self, block, layers, num_classes=1000, groups=1,
                 zero_init_residual=False, width_per_group=64,
                 replace_stride_with_dilation=None, norm_layer=None,
                 mean=None, std=None, **kwargs):
        super(NormResNet, self).__init__()

        self.norm = Normalization(mean, std)
        if norm_layer is None:
            norm_layer = nn.BatchNorm2d
        self._norm_layer = norm_layer

        self.inplanes = 64
        self.dilation = 1
        if replace_stride_with_dilation is None:
            # each element in the tuple indicates if we should replace
            # the 2x2 stride with a dilated convolution instead
            replace_stride_with_dilation = [False, False, False]
        if len(replace_stride_with_dilation) != 3:
            raise ValueError("replace_stride_with_dilation should be None "
                             "or a 3-element tuple, got {}".format(
                                 replace_stride_with_dilation))
        self.groups = groups
        self.base_width = width_per_group
        self.conv1 = nn.Conv2d(3, self.inplanes, kernel_size=7, stride=2,
                               padding=3, bias=False)
        self.bn1_adv = norm_layer(self.inplanes)
        self.bn1_clean = norm_layer(self.inplanes)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2,
                                       dilate=replace_stride_with_dilation[0])
        self.layer3 = self._make_layer(block, 256, layers[2], stride=2,
                                       dilate=replace_stride_with_dilation[1])
        self.layer4 = self._make_layer(block, 512, layers[3], stride=2,
                                       dilate=replace_stride_with_dilation[2])
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(512 * block.expansion, num_classes)

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out',
                                        nonlinearity='relu')
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

        # Zero-initialize the last BN in each residual branch,
        # so that the residual branch starts with zeros, and each residual
        # block behaves like an identity.
        # This improves the model by 0.2~0.3%
        # according to https://arxiv.org/abs/1706.02677
        if zero_init_residual:
            for m in self.modules():
                if isinstance(m, Bottleneck):
                    nn.init.constant_(m.bn3_adv.weight, 0)
                    nn.init.constant_(m.bn3_clean.weight, 0)
                    # type: ignore[arg-type]
                elif isinstance(m, BasicBlock):
                    nn.init.constant_(m.bn2_adv.weight, 0)
                    nn.init.constant_(m.bn2_clean.weight, 0)
                    # type: ignore[arg-type]

    def _make_layer(self, block, planes, blocks, stride=1, dilate=False):
        norm_layer = self._norm_layer
        downsample = None
        previous_dilation = self.dilation
        if dilate:
            self.dilation *= stride
            stride = 1
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                conv1x1(self.inplanes, planes * block.expansion, stride),
                norm_layer(planes * block.expansion),
            )

        layers = [block(self.inplanes, planes, stride, downsample, self.groups,
                        self.base_width, previous_dilation, norm_layer)]
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(block(self.inplanes, planes,
                                groups=self.groups,
                                base_width=self.base_width,
                                dilation=self.dilation,
                                norm_layer=norm_layer))

        return nn.Sequential(*layers)

    def forward(self, x, is_adv=False):
        # See note [TorchScript super()]
        x = self.norm(x)
        x = self.conv1(x)
        x = self.bn1_adv(x) if is_adv else self.bn1_clean(x)
        x = self.relu(x)
        x = self.maxpool(x)

        x = self.layer1(x, is_adv)
        x = self.layer2(x, is_adv)
        x = self.layer3(x, is_adv)
        x = self.layer4(x, is_adv)

        x = self.avgpool(x)
        x = torch.flatten(x, 1)
        x = self.fc(x)

        return x


@Networks.register_module('NormResNet18')
class NormDualBNResNet18(NormResNet):
    def __init__(self, num_classes=1000, block=BasicBlock, layers=[2, 2, 2, 2],
                 mean=None, std=None, **kwargs):
        super(NormDualBNResNet18, self).__init__(
            block=block, num_classes=num_classes, layers=layers,
            mean=mean, std=std,
        )


# if __name__ == '__main__':
    # model = NormDualBNResNet18()
    # print(model)

# def _init_weight(m):
#     classname = m.__class__.__name__
#     if classname.find('Conv') != -1:
#         nn.init.kaiming_normal_(m.weight.data)
#     elif classname.find('BatchNorm') != -1 and len(m.weight.shape) > 1:
#         nn.init.kaiming_normal_(m.weight.data)
#         nn.init.constant_(m.weight.bias)


# @Networks.register_module('Norm_ResNet18')
# class resnet18(nn.Module):
#     def __init__(self, num_classes, mean=None, std=None, **kwargs):
#         super(resnet18, self).__init__()
#         self.n_class = num_classes

#         self.norm = Normalization(mean, std)
#         self.encoder = nn.Sequential(
#             *list(models.resnet18(pretrained=False).children())[:-1]
#             + [nn.Flatten()]
#         )
#         self.classifier = nn.Linear(in_features=512,
#                                     out_features=num_classes,
#                                     bias=False)
#         self.encoder.apply(_init_weight)

#     def forward(self, x):
#         x_norm = self.norm(x)
#         f = self.encoder(x_norm)
#         y = self.classifier(f)

#         return y


# @Networks.register_module('Norm_ResNet18_Small')
# class resnet18_small(nn.Module):
#     def __init__(self, num_classes, mean=None, std=None, **kwargs):
#         super(resnet18_small, self).__init__()
#         self.n_class = num_classes

#         self.norm = Normalization(mean, std)
#         self.encoder = nn.Sequential(
#             *list(models.resnet18(pretrained=False).children())[:-1]
#             + [nn.Flatten()]
#         )
#         self.encoder[0] = nn.Conv2d(3, 64, 3, 1, 1, bias=False)
#         self.encoder[2] = nn.Identity()
#         self.classifier = nn.Linear(
#             in_features=512, out_features=num_classes, bias=False)
#         self.encoder.apply(_init_weight)

#     def forward(self, x):
#         x_norm = self.norm(x)
#         f = self.encoder(x_norm)
#         y = self.classifier(f)

#         return y
