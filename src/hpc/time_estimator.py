"""
HPC Time Estimator - Estimate simulation walltime requirements
"""
import logging
from typing import Dict, Any
from langchain.tools import tool

logger = logging.getLogger(__name__)


class SimulationTimeEstimate:
    """Estimate simulation time requirements"""
    
    def __init__(
        self,
        production_ns: float = 10.0,
        timestep_ps: float = 0.002,
        frame_interval_ps: float = 10.0,
        system_size: int = 50000
    ):
        self.production_ns = production_ns
        self.timestep_ps = timestep_ps
        self.frame_interval_ps = frame_interval_ps
        self.system_size = system_size
    
    def calculate_steps(self) -> int:
        """Calculate total number of MD steps"""
        return int(self.production_ns * 1000 / self.timestep_ps)
    
    def estimate_walltime_hours(self) -> float:
        """
        Estimate walltime in hours based on system size and GPU performance.
        Rule of thumb: ~1 ns/day for 50k atoms on modern GPU
        """
        # Base performance: 1 ns/day (24 hours) for 50k atoms
        base_performance_ns_per_hour = 1.0 / 24.0
        
        # Scale by system size (roughly linear)
        size_factor = self.system_size / 50000.0
        
        # Estimate production time
        production_hours = self.production_ns / base_performance_ns_per_hour * size_factor
        
        # Add equilibration time (typically 10-20% of production)
        equilibration_hours = production_hours * 0.15
        
        # Add buffer for minimization and overhead (10%)
        total_hours = (production_hours + equilibration_hours) * 1.1
        
        return total_hours
    
    def format_slurm_time(self) -> str:
        """Format estimated time as SLURM time limit (days-hours:min:sec)"""
        total_hours = self.estimate_walltime_hours()
        days = int(total_hours // 24)
        hours = int(total_hours % 24)
        minutes = int((total_hours % 1) * 60)
        return f"{days}-{hours:02d}:{minutes:02d}:00"


@tool
def estimate_simulation_time(
    production_ns: float = 10.0,
    system_size: int = 50000,
    timestep_ps: float = 0.002
) -> Dict[str, Any]:
    """
    Estimate simulation walltime based on system size and simulation length.
    
    Args:
        production_ns: Production simulation length in nanoseconds
        system_size: Number of atoms in the system
        timestep_ps: Integration timestep in picoseconds
        
    Returns:
        Dict with time estimates and SLURM time format
        
    Example:
        >>> estimate_simulation_time(production_ns=50, system_size=80000)
        {
            "estimated_hours": 72.6,
            "slurm_time": "3-00:36:00",
            "total_steps": 25000000
        }
    """
    try:
        estimate = SimulationTimeEstimate(
            production_ns=production_ns,
            system_size=system_size,
            timestep_ps=timestep_ps
        )
        
        total_steps = estimate.calculate_steps()
        estimated_hours = estimate.estimate_walltime_hours()
        slurm_time = estimate.format_slurm_time()
        
        return {
            "success": True,
            "production_ns": production_ns,
            "system_size": system_size,
            "total_steps": total_steps,
            "estimated_hours": round(estimated_hours, 1),
            "slurm_time": slurm_time,
            "performance_note": f"~{round(production_ns/estimated_hours*24, 1)} ns/day estimated",
            "message": f"Estimated walltime: {slurm_time} ({estimated_hours:.1f} hours)"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Time estimation failed: {e}"
        }
