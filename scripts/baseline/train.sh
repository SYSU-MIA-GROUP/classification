export PYTHONPATH=$PYTHONPATH:$HOME/Projects/classification

# Distributed Training
# CUDA_VISIBLE_DEVICES=$1 python3 -W ignore -m torch.distributed.launch\
#     --nproc_per_node=$2 --master_addr 127.0.0.111 --master_port 30000 \
#     train.py --config_path "configs/miniIN3_0.02/r18_h.yaml"

# Baseline
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r18.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r18_OS.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r18_RS.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r18_RW.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r34.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r18_CB0.99.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r18_CB0.99_focal1.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r18_focal1.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r18_focal2.yaml'

# Center Loss
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
        # --config_path 'configs/miniIN3_0.02/r18_center_alpha0.001_cos.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/r18_center_alpha0.001_eu.yaml'

# Augments
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/augments/r18_noTF.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/augments/r18_cj.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/augments/r18_hflip.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/augments/r18_vflip.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/augments/r18_rscrop.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/augments/r18_rot.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/augments/r18_tsl.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/augments/r18_scale.yaml'
# CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
#         --config_path 'configs/miniIN3_0.02/augments/r18_shear.yaml'

# Toy
CUDA_VISIBLE_DEVICES=$1 python3 train.py --local_rank -1\
        --config_path 'configs/miniIN3_0.02/tr18.yaml'
