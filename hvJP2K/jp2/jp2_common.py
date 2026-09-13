from glymur import version


def first_box(boxes, box_id):
    for box in boxes:
        if box is not None and box.box_id == box_id:
            return box
    return None


def require_openjpeg():
    if version.openjpeg_version_tuple < (2, 4):
        raise RuntimeError(
            "OpenJPEG 2.4 or newer is required; found {0}".format(
                version.openjpeg_version
            )
        )
