from torch import nn

from mwptoolkit.loss.abstract_loss import AbstractLoss
class NLLLoss(AbstractLoss):
    
    _NAME = "Avg NLLLoss"

    def __init__(self, weight=None, mask=None, size_average=True):
        self.mask = mask
        self.size_average = size_average
        if mask is not None:
            if weight is None:
                raise ValueError("Must provide weight with a mask.")
            weight[mask] = 0
        #weight = weight.cuda()
        super(NLLLoss, self).__init__(
              self._NAME,
              nn.NLLLoss(weight=weight, reduction="mean"))
    
    def get_loss(self):
        if isinstance(self.acc_loss, int):
            return 0
        loss = self.acc_loss.item()#.data[0]
        if self.size_average:
            loss /= self.norm_term
        return loss

    def eval_batch(self, outputs, target):
        #print (outputs.size(), target.size())
        self.acc_loss += self.criterion(outputs, target)
        self.norm_term += 1