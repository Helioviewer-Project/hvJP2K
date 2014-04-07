
import pkg_resources

def hv_schematron():
    return pkg_resources.resource_filename(__name__, 'hv.sch')
