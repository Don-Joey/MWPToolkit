class WarmUpScheduler():
    def __init__(self,optimizer, init_lr, d_model, n_warmup_steps):
        self.optimizer=optimizer
        self.init_lr=init_lr
        self.d_model=d_model
        self.n_warmup_steps=n_warmup_steps
        self._steps = 0
    
    def step(self):
        r"""Update parameters"""
        self._update_learning_rate()
        #self.optimizer.step()
    
    def _update_learning_rate(self):
        r"""Learning rate scheduling per step"""
        self._steps += 1
        lr = self.init_lr * self._get_lr_scale()

        # for param_group in self._optimizer.param_groups:
        #     param_group['lr'] = lr
    
    def _get_lr_scale(self):
        d_model = self.d_model
        n_steps, n_warmup_steps = self._steps, self.n_warmup_steps
        return (d_model ** -0.5) * min(n_steps ** (-0.5), n_steps * n_warmup_steps ** (-1.5))
    
    def zero_grad(self):
        self._optimizer.zero_grad()

    def state_dict(self):
        return self._optimizer.state_dict()
    
    def get_lr(self):
        lr = self.init_lr * self._get_lr_scale()
        return [lr]

if __name__ == '__main__':
    from matplotlib import pyplot as plt
    optim=WarmUpScheduler(None,0.3,3032,1500)
    lr=[]
    for x in range(100):
        for y in range(300):
            optim.step()
            lr.append(optim.get_lr()[0])
    
    plt.plot(lr)
    plt.show()