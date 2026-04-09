import psr.runner
import os
import sys
from typing import Union,List
import subprocess

import subprocess

def run_psrio(executable_path, script_path, output_path, sddp_case_path):
    cmd = (
        f'"{executable_path}" '
        f'-r "{script_path}" '
        f'-o "{output_path}" '
        f'"{sddp_case_path}" '
    )

    subprocess.run(cmd, shell=True, check=True)

run_psrio(r"C:\PSR\GraphModule\Oper\psrplot\psrio\PSRIO.exe", r"D:\01-Repositories\AI\mcp-psr-output-analysis\psrio\psrio.lua", r"D:\01-Repositories\AI\TCC\Casos\02_PMPO_ENERO2024_Abdu\01_Caso_Base\results",  r"D:\01-Repositories\AI\TCC\Casos\02_PMPO_ENERO2024_Abdu\01_Caso_Base")