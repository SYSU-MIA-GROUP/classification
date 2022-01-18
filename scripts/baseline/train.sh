export PYTHONPATH=$PYTHONPATH:$HOME/Projects/classification

# Distributed Training
CUDA_VISIBLE_DEVICES=0,1 python3 -W ignore -m torch.distributed.launch\
    --nproc_per_node=2 --master_addr 127.0.0.111 --master_port 30006 \
    train.py --config_path "configs/CF100_0.01/r32.yaml"

# Baseline
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1 --config_path $2 --seed $3
# CUDA_VISIBLE_DEVICES=0 python3 train.py --local_rank -1 --config_path 'configs/CIFAR10_0.02/r32.yaml' --seed 0
# CUDA_VISIBLE_DEVICES=0 python3 train.py --local_rank -1 --config_path 'configs/CIFAR10_0.02/r32.yaml' --seed 1
# CUDA_VISIBLE_DEVICES=0 python3 train.py --local_rank -1 --config_path 'configs/CIFAR10_0.02/r32.yaml' --seed 2

# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1 --config_path 'configs/CIFAR10_0.01/r32.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1 --config_path 'configs/CIFAR10_0.01/r32_RS.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1 --config_path 'configs/CIFAR10_0.01/r32_RW.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1 --config_path 'configs/CIFAR10_0.01/r32_OS.yaml'
