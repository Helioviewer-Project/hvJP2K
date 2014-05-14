
def first_box(boxes, box_id):
    for box in boxes:
        if box is not None and box.box_id == box_id:
            return box
    return None
