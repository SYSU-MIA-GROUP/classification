export PYTHONPATH=$HOME/Projects/classification

# Distributed Training
OMP_NUM_THREADS=1 CUDA_VISIBLE_DEVICES=$1 torchrun --nproc_per_node=$2 \
    --master_addr 127.0.0.1 --master_port 30000 train_2opt.py --config_path $3

# Single-GPU Training
# CUDA_VISIBLE_DEVICES=$1 python3 train_2opt.py --config_path $2
