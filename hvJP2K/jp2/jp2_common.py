
def first_box(sup, box_id):
    for box in sup.box:
        if box.box_id == box_id:
            return box
    return None
