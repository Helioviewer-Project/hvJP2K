
# cython: profile=False
# cython: infer_types=True
# cython: boundscheck=False
# cython: wraparound=False

from libc.string cimport strcmp


cpdef first_box(boxes, const char *box_id):
    cdef const char *_box_id
    cdef int i, n = len(boxes)
    for i in range(n):
        box = boxes[i]
        _box_id = box.box_id
        if strcmp(_box_id, box_id) == 0:
            return box

    return None
