
from importlib.resources import files

def hv_schematron():
    return str(files(__name__).joinpath('hv.sch'))
