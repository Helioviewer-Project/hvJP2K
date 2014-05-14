
# cython: profile=False
# cython: infer_types=True
# cython: boundscheck=False
# cython: wraparound=False


cpdef first_box(list boxes, str box_id):
    cdef Py_ssize_t i, n = len(boxes)

    for i in range(n):
        box = boxes[i]
        if box is not None and box.box_id == box_id:
            return box

    return None
