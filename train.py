import argparse
import os
import copy

import torch
from torch import nn
import torch.optim as optim
import torch.backends.cudnn as cudnn
import torch.utils.data as data_utils
from tqdm import tqdm

from Dataset import *
from BaseDataset import * 
from model.SRCNN import *
from model.Unet import * 
from image_utils.utils import * 

parser = argparse.ArgumentParser()
parser.add_argument('--outputs-dir', type=str, required=True, default='/Users/haoruilong/BA_code/SR_for_CT_image_of_Batteries/outputs')
parser.add_argument('-s', '--size', dest='size', type = int, help='The size of each tile in pages in tiff', default=256)
parser.add_argument('-lr', '--lr', dest='lr', type=float, default=1e-4)
parser.add_argument('-ep', '--num_epochs', dest='num_epochs', type=int, default=100)
parser.add_argument('-b', '--batch_size', dest='batch_size', type=int, default=32)
args = parser.parse_args()
"""
# Simple dataset 
# Load dataset
input_path = "/Users/haoruilong/Dataset_for_Battery/Pristine/PTY_raw/bin_2"
label_path = "/Users/haoruilong/Dataset_for_Battery/Pristine/PTY_raw/original"

dataset = MyDataset(input_path, label_path)
dataloader = MyDataLoader(dataset, batch_size=5, shuffle=True)

# Test if DataLoader successfully loads the data
for binning, image_label in dataloader:
    print(binning.shape)
    print(image_label.shape)

    for i in range(binning.size(0)):
        binning_tensor = binning[i]
        bin = transforms.ToPILImage()(binning_tensor)
        bin.save(f'./images/binning_{i}.png', 'PNG')
    
    for j in range(image_label.size(0)):
        image_label_tensor = image_label[i]
        label = transforms.ToPILImage()(image_label_tensor)
        label.save(f'./images/image_label_{j}.png', 'PNG')
    break
"""
# Prepare dataloader for training and testing
# Data path
data_root = '/Users/haoruilong/BA_code/SR_for_CT_image_of_Batteries'
dataset_dir = ['/Dataset/Pristine']

# Prepare configurations for dataset
cfgs_path_p = data_root + '/configs/preprocess.yaml'
cfgs_path_t = data_root + '/configs/transform.yaml'

if os.path.exists(cfgs_path_p):
    preprocess_cfgs = OmegaConf.load(cfgs_path_p)
else:
    preprocess_cfgs = None

if os.path.exists(cfgs_path_t):
    transform_cfgs = OmegaConf.load(cfgs_path_t)
else:
    preprocess_cfgs = None

# Dataset for all, size: 256*256
mydataset = BaseDataset('SR', 'train', args.size, dataset_dir, data_root, None, preprocess_cfgs)

# Data splitting
length_dataset = mydataset.__len__()
train_size = int(0.8 * length_dataset)
test_size = length_dataset - train_size

train_dataset, test_dataset = data_utils.random_split(mydataset, [train_size, test_size])
# Apply train and test dataset in dataloader
train_dataloader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
test_dataloader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=True)

"""
# Test if dataloader successful is
for batch in train_dataloader:
    inputs, labels, _ = batch
"""


# Train the model
cudnn.benchmark = True
device = torch.device("mps")
# If the model is SRCNN
model = SRCNN().to(device)
criterion = nn.MSELoss()
optimizer = optim.Adam([
    {'params': model.conv1.parameters()},
    {'params': model.conv2.parameters()},
    {'params': model.conv3.parameters(), 'lr': args.lr * 0.1}
    ], lr=args.lr)

best_weight = copy.deepcopy(model.state_dict())
best_epoch = 0
best_psnr = 0.0

for epoch in range(args.num_epochs):
    model.train()
    epoch_losses = AverageMeter()

    with tqdm(total=(train_dataset.__len__() - train_dataset.__len__() % args.batch_size)) as t:
        t.set_description('epoch: {}/{}'.format(epoch, args.num_epochs - 1))
        
        for batch in train_dataloader:
            inputs, labels = batch

            inputs = inputs.to(device)
            labels = labels.to(device)

            preds = model(inputs)

            loss = criterion(preds, labels)

            epoch_losses.update(loss.item(), len(inputs))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            t.set_postfix(loss='{:.6f}'.format(epoch_losses.avg))
            t.update(len(inputs))
    
    torch.save(model.state_dict(), os.path.join(args.outputs_dir, 'epoch_{}.pth'.format(epoch)))

    model.eval()
    epoch_psnr = AverageMeter()

    for batch in test_dataloader:
        inputs, labels = batch

        inputs = inputs.to(device)
        labels = labels.to(device)

        with torch.no_grad():
            preds = model(inputs).clamp(0.0, 0.1)

        epoch_psnr.update(calc_psnr(preds, labels), len(inputs))
    
    print('eval psnr: {:.2f}'.format(epoch_psnr.avg))

    if epoch_psnr > best_psnr:
        best_epoch = epoch
        best_psnr = epoch_psnr.avg
        best_weight = copy.deepcopy(model.state_dict())
    
print('best epoch: {}, psnr: {:.2f}'.format(best_epoch, best_psnr))
torch.save(best_weight, os.path.join(args.outputs_dir, 'best.pth'))