import torch
from sb.nn import utils

from .losses import _make_bwd_sde_step, _make_fwd_sde_step


def get_mean_log_var(model, x, t, dt, return_drift: bool = False):
    log_var = torch.log(torch.ones_like(x) * 2.0 * dt)
    output = model(x, t)
    
    if output.contains('log_var'):
        log_var = log_var + output.log_var
        if log_var.isnan().any():
            raise ValueError("Log var is Nan")
    
    if output.drift.isnan().any():
        raise ValueError("Drift is Nan")
    mean = x + output.drift * dt
    
    if return_drift:
        return output.drift, mean, log_var

    return mean, log_var


@torch.no_grad()
def sample_trajectory(model, x_start, direction, dt, n_steps, t_max, 
                      only_last: bool = False, return_timesteps: bool = False,
                      matching_method: str = "ll"):
    assert direction in {"forward", "backward"}
    trajectory = [x_start]
    timesteps = [f"{t_max if direction == 'backward' else 0}"]

    for t_step in (
            torch.linspace(dt, t_max, n_steps).flip(-1) \
            if direction == 'backward' \
            else torch.linspace(0, t_max - dt, n_steps)
        ):
        shift = - dt if direction == "backward" else + dt
        timesteps.append(f"{t_step.item() + shift:.3f}")
        
        t = torch.ones(x_start.size(0), device=x_start.device) * t_step
        mean, log_var = get_mean_log_var(model, trajectory[-1], t, dt)
        noise_std = log_var.exp().sqrt()

        if matching_method == "sde":
            if direction == "backward":
                x_new = _make_bwd_sde_step(mean, trajectory[-1], dt, 1.42, noise_std)
            else:
                x_new = _make_fwd_sde_step(mean, trajectory[-1], dt, 1.42, noise_std)

        if matching_method in {"ll", "mean"}:
            x_new = mean + torch.randn_like(mean) * noise_std
        
        elif matching_method == "score":
            x_new = trajectory[-1] + mean + torch.randn_like(mean) * noise_std
        
        trajectory.append(x_new)

    
    if return_timesteps:
        return trajectory, timesteps
    
    if only_last:
        return trajectory[-1]
    
    return trajectory


class ReferenceProcess:
    def __init__(self, alpha: float, gamma: float):
        self.alpha = alpha
        self.gamma = gamma
    
    def __call__(self, x, t):
        return utils.ModelOutput(drift=-self.alpha * self.gamma * x)
    

class ReferenceProcess2:
    def __init__(self, alpha: float):
        self.alpha = alpha
    
    def __call__(self, x, t):
        return utils.ModelOutput(drift= - self.alpha * x)
