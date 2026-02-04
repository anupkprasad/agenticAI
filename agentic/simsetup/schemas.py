"""
Pydantic schemas for simulation setup validation
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field, validator


class TopologyBuildInput(BaseModel):
    """Input schema for topology generation"""
    pdb_file: str = Field(..., description="Path to cleaned PDB file")
    force_field: str = Field(default="amber99sb-ildn", description="GROMACS force field")
    water_model: str = Field(default="tip3p", description="Water model (tip3p, spce, tip4p)")
    output_file: Optional[str] = Field(None, description="Output coordinate file path")
    topology_file: Optional[str] = Field(None, description="Output topology file path")


class BoxBuildInput(BaseModel):
    """Input schema for simulation box creation"""
    coordinate_file: str = Field(..., description="Input coordinate file (.gro)")
    box_type: Literal["cubic", "dodecahedron", "octahedron"] = Field(
        default="cubic", 
        description="Box shape"
    )
    box_distance: float = Field(default=1.0, description="Distance from solute to box edge (nm)")
    output_file: Optional[str] = Field(None, description="Output coordinate file")


class SolvateInput(BaseModel):
    """Input schema for system solvation"""
    coordinate_file: str = Field(..., description="Input coordinate file (.gro)")
    topology_file: str = Field(..., description="Topology file (.top)")
    water_model: str = Field(default="spc216", description="Water configuration")
    output_file: Optional[str] = Field(None, description="Output coordinate file")


class IonAdditionInput(BaseModel):
    """Input schema for ion addition"""
    coordinate_file: str = Field(..., description="Input coordinate file (.gro)")
    topology_file: str = Field(..., description="Topology file (.top)")
    mdp_file: str = Field(..., description="MDP parameter file for grompp")
    neutral: bool = Field(default=True, description="Neutralize system charge")
    concentration: float = Field(default=0.15, description="Salt concentration (M)")
    output_file: Optional[str] = Field(None, description="Output coordinate file")
    
    @validator("concentration")
    def validate_concentration(cls, v):
        if v < 0 or v > 2.0:
            raise ValueError("Concentration must be between 0 and 2.0 M")
        return v


class MDPGenerationInput(BaseModel):
    """Input schema for MDP file generation"""
    mdp_type: Literal["minim", "nvt", "npt", "md", "ions"] = Field(
        default="minim",
        description="Type of simulation"
    )
    temperature: float = Field(default=300.0, description="Temperature (K)")
    pressure: float = Field(default=1.0, description="Pressure (bar)")
    nsteps: int = Field(default=50000, description="Number of simulation steps")
    output_file: Optional[str] = Field(None, description="Output MDP file path")
    
    @validator("temperature")
    def validate_temperature(cls, v):
        if v < 0 or v > 1000:
            raise ValueError("Temperature must be between 0 and 1000 K")
        return v
    
    @validator("nsteps")
    def validate_nsteps(cls, v):
        if v < 0:
            raise ValueError("nsteps must be positive")
        return v


class AmberConversionInput(BaseModel):
    """Input schema for AMBER to GROMACS conversion"""
    prmtop_file: str = Field(..., description="AMBER parameter/topology file (.prmtop)")
    inpcrd_file: str = Field(..., description="AMBER coordinate file (.inpcrd/.rst7)")
    output_prefix: Optional[str] = Field(None, description="Output file prefix")


class SetupOutput(BaseModel):
    """Output schema for setup operations"""
    success: bool = Field(..., description="Operation success status")
    output_file: Optional[str] = Field(None, description="Primary output file")
    topology_file: Optional[str] = Field(None, description="Topology file if generated")
    message: str = Field(..., description="Status message")
    warnings: Optional[list] = Field(default_factory=list, description="Warning messages")
    error: Optional[str] = Field(None, description="Error message if failed")
