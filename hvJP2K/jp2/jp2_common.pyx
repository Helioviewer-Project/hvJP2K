
#cython: boundscheck=False
#cython: wraparound=False

from libc.string cimport strcmp


cpdef first_box(boxes, const char *box_id):
    cdef const char *_box_id
    for box in boxes:
        _box_id = box.box_id
        if strcmp(_box_id, box_id) == 0:
            return box

    return None
