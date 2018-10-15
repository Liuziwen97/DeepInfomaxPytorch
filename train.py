import torch
from models import Encoder, GlobalDiscriminator, LocalDiscriminator, PriorDiscriminator
from torchvision.datasets.cifar import CIFAR10
from torch.utils.data import DataLoader
from torchvision.transforms import ToTensor
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam
from tqdm import tqdm
from pathlib import Path


class DeepInfoMaxLoss(nn.Module):
    def __init__(self, alpha=0.5, beta=1.0, gamma=0.1):
        super().__init__()
        self.global_d = GlobalDiscriminator()
        self.local_d = LocalDiscriminator()
        self.prior_d = PriorDiscriminator()
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma

    def forward(self, y, M, M_prime):

        # see appendix 1A of https://arxiv.org/pdf/1808.06670.pdf

        y_exp = y.unsqueeze(-1).unsqueeze(-1)
        y_exp = y_exp.expand(-1, -1, 26, 26)

        y_M = torch.cat((M, y_exp), dim=1)
        y_M_prime = torch.cat((M_prime, y_exp), dim=1)

        Ej = -F.softplus(-self.local_d(y_M)).mean()
        Em = F.softplus(self.local_d(y_M_prime)).mean()
        LOCAL = (Em - Ej) * self.beta

        Ej = -F.softplus(-self.global_d(y, M)).mean()
        Em = F.softplus(self.global_d(y, M_prime)).mean()
        GLOBAL = (Em - Ej) * self.alpha

        prior = torch.rand_like(y)

        term_a = torch.log(self.prior_d(prior)).mean()
        term_b = torch.log(1.0 - self.prior_d(y)).mean()
        PRIOR = - (term_a + term_b) * self.gamma

        return LOCAL + GLOBAL + PRIOR


if __name__ == '__main__':

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    batch_size = 128

    # image size 3, 32, 32
    # batch size must be an even number
    # shuffle must be True
    cifar_10_train_dt = CIFAR10(r'c:\data\tv',  download=True, transform=ToTensor())
    cifar_10_train_l = DataLoader(cifar_10_train_dt, batch_size=batch_size, shuffle=True, drop_last=True,
                                  pin_memory=torch.cuda.is_available())

    encoder = Encoder().to(device)
    optim = Adam(encoder.parameters())
    loss_fn = DeepInfoMaxLoss().to(device)

    for epoch in range(10):
        batch = tqdm(cifar_10_train_l, total=len(cifar_10_train_dt) // batch_size)
        for x, target in batch:
            x = x.to(device)

            optim.zero_grad()
            y, M = encoder(x)
            # rotate images to create pairs for comparison
            M_prime = torch.cat((M[1:], M[0].unsqueeze(0)), dim=0)
            loss = loss_fn(y, M, M_prime)
            batch.set_description('Loss: ' + str(loss.item()))
            loss.backward()
            optim.step()

        file = Path(r'c:\data\deepinfomax\models\run1\encoder' + str(epoch))
        file.parent.mkdir(parents=True, exist_ok=True)
        torch.save(encoder.state_dict(), str(file))
