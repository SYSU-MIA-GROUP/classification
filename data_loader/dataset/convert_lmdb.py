# -*- coding: utf-8 -*-
# @Author  : DevinYang(pistonyang@gmail.com)
"""This file should not be included in __init__"""

__all__ = ['get_key', 'load_pyarrow', 'dumps_pyarrow',
           'generate_lmdb_dataset', 'raw_reader']

import lmdb
import os
import pyarrow
from tqdm import tqdm
from pudb import set_trace
from torch.utils.data import DataLoader, Dataset
from data_loader.dataset.builder import build_dataset


def get_key(index):
    return u'{}'.format(index).encode('ascii')


def raw_reader(path):
    with open(path, 'rb') as f:
        bin_data = f.read()
    return bin_data


def dumps_pyarrow(obj):
    return pyarrow.serialize(obj).to_buffer()


def load_pyarrow(buf):
    assert buf is not None, 'buf should not be None.'
    return pyarrow.deserialize(buf)


def generate_lmdb_dataset(data_set: Dataset,
                          save_dir: str,
                          name: str,
                          num_workers=0,
                          max_size_rate=1.0,
                          write_frequency=5000):

    data_loader = DataLoader(data_set,
                             num_workers=num_workers,
                             collate_fn=lambda x: x)  # bs=1
    num_samples = len(data_set)
    os.makedirs(save_dir, exist_ok=True)
    lmdb_path = os.path.join(save_dir, '{}.lmdb'.format(name))
    db = lmdb.open(lmdb_path,
                   subdir=False,
                   map_size=int(1099511627776 * max_size_rate),
                   readonly=False,
                   meminit=True,
                   map_async=True)
    txn = db.begin(write=True)
    for idx, data in enumerate(tqdm(data_loader)):
        txn.put(get_key(idx), dumps_pyarrow(data[0]))  # bs=1
        if idx % write_frequency == 0 and idx > 0:
            txn.commit()
            txn = db.begin(write=True)
    txn.put(b'__len__', dumps_pyarrow(num_samples))
    try:
        classes = data_set.classes
        class_to_idx = data_set.class_to_idx
        txn.put(b'classes', dumps_pyarrow(classes))
        txn.put(b'class_to_idx', dumps_pyarrow(class_to_idx))
    except AttributeError:
        pass

    txn.commit()
    db.sync()
    db.close()


if __name__ == "__main__":
    dataset_name = 'ImbalanceCIFAR10'
    save_dir = "~/Data/cifar10"
    train = True

    dataset_params = {
        'data_root': save_dir,
        'train': True,
        'imb_type': 'exp',
        'imb_factor': 0.01,
    }
    lmdb_name = "train" if train else "test"

    dset = build_dataset(dataset_name, **dataset_params)
    generate_lmdb_dataset(dset, save_dir, lmdb_name, num_workers=4)
