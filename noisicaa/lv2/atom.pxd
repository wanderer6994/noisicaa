# @begin:license
#
# Copyright (c) 2015-2019, Benjamin Niemann <pink@odahoda.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# @end:license

from libc.stdint cimport uint32_t, int32_t, int64_t, uint8_t, intptr_t

from .urid cimport LV2_URID, LV2_URID_Map, URID_Map_Feature
from .urid_mapper cimport PyURIDMapper


cdef extern from "stdbool.h" nogil:
    ctypedef bint bool


cdef extern from "lv2/lv2plug.in/ns/ext/atom/atom.h" nogil:
    # The header of an atom:Atom.
    ctypedef struct LV2_Atom:
        uint32_t size  # Size in bytes, not including type and size.
        uint32_t type  # Type of this atom (mapped URI).

    # An atom:Int or atom:Bool.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Int:
        LV2_Atom atom  # Atom header.
        int32_t  body  # Integer value.

    # An atom:Long.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Long:
        LV2_Atom atom  # Atom header.
        int64_t  body  # Integer value.

    # An atom:Float.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Float:
        LV2_Atom atom  # Atom header.
        float    body  # Floating point value.

    # An atom:Double.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Double:
        LV2_Atom atom  # Atom header.
        double   body  # Floating point value.

    # An atom:Bool.  May be cast to LV2_Atom.
    ctypedef LV2_Atom_Int LV2_Atom_Bool

    # An atom:URID.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_URID:
        LV2_Atom atom  # Atom header.
        uint32_t body  # URID.

    # An atom:String.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_String:
        LV2_Atom atom  # Atom header.
        # Contents (a null-terminated UTF-8 string) follow here.

    # The body of an atom:Literal.
    ctypedef struct LV2_Atom_Literal_Body:
        uint32_t datatype  # Datatype URID.
        uint32_t lang      # Language URID.
        # Contents (a null-terminated UTF-8 string) follow here.

    # An atom:Literal.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Literal:
        LV2_Atom              atom  # Atom header.
        LV2_Atom_Literal_Body body  # Body.

    # An atom:Tuple.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Tuple:
        LV2_Atom atom  # Atom header.
        # Contents (a series of complete atoms) follow here.

    # The body of an atom:Vector.
    ctypedef struct LV2_Atom_Vector_Body:
        uint32_t child_size  # The size of each element in the vector.
        uint32_t child_type  # The type of each element in the vector.
        # Contents (a series of packed atom bodies) follow here.

    # An atom:Vector.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Vector:
        LV2_Atom             atom  # Atom header.
        LV2_Atom_Vector_Body body  # Body.

    # The body of an atom:Property (e.g. in an atom:Object).
    ctypedef struct LV2_Atom_Property_Body:
        uint32_t key      # Key (predicate) (mapped URI).
        uint32_t context  # Context URID (may be, and generally is, 0).
        LV2_Atom value    # Value atom header.
        # Value atom body follows here.

    # An atom:Property.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Property:
        LV2_Atom               atom  # Atom header.
        LV2_Atom_Property_Body body  # Body.

    # The body of an atom:Object. May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Object_Body:
        uint32_t id     # URID, or 0 for blank.
        uint32_t otype  # Type URID (same as rdf:type, for fast dispatch).
        # Contents (a series of property bodies) follow here.

    # An atom:Object.  May be cast to LV2_Atom.
    ctypedef struct LV2_Atom_Object:
        LV2_Atom             atom  # Atom header.
        LV2_Atom_Object_Body body  # Body.

    # The header of an atom:Event.  Note this type is NOT an LV2_Atom.
    ctypedef union LV2_Atom_Event_Time:
        int64_t frames  # Time in audio frames.
        double  beats   # Time in beats.

    ctypedef struct LV2_Atom_Event:
        # Time stamp.  Which type is valid is determined by context.
        LV2_Atom_Event_Time time
        LV2_Atom body  # Event body atom header.
        # Body atom contents follow here.

    # The body of an atom:Sequence (a sequence of events).
    #
    # The unit field is either a URID that described an appropriate time stamp
    # type, or may be 0 where a default stamp type is known.  For
    # LV2_Descriptor::run(), the default stamp type is audio frames.
    #
    # The contents of a sequence is a series of LV2_Atom_Event, each aligned
    # to 64-bits, e.g.:
    # | Event 1 (size 6)                              | Event 2
    # |       |       |       |       |       |       |       |       |
    # | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | | |
    # |FRAMES |SUBFRMS|TYPE   |SIZE   |DATADATADATAPAD|FRAMES |SUBFRMS|...
    ctypedef struct LV2_Atom_Sequence_Body:
        uint32_t unit  # URID of unit of event time stamps.
        uint32_t pad   # Currently unused.
        # Contents (a series of events) follow here.

    # An atom:Sequence.
    ctypedef struct LV2_Atom_Sequence:
        LV2_Atom               atom  # Atom header.
        LV2_Atom_Sequence_Body body  # Body.


cdef extern from "lv2/lv2plug.in/ns/ext/atom/util.h" nogil:
    uint32_t lv2_atom_total_size(const LV2_Atom* atom)
    bool lv2_atom_is_null(const LV2_Atom* atom)
    bool lv2_atom_equals(const LV2_Atom* a, const LV2_Atom* b)

    LV2_Atom_Event* lv2_atom_sequence_begin(const LV2_Atom_Sequence_Body* body)
    LV2_Atom_Event* lv2_atom_sequence_end(const LV2_Atom_Sequence_Body* body,
                                          uint32_t size)
    bool lv2_atom_sequence_is_end(const LV2_Atom_Sequence_Body* body,
                                  uint32_t                      size,
                                  const LV2_Atom_Event*         i)
    LV2_Atom_Event* lv2_atom_sequence_next(const LV2_Atom_Event* i)

    void lv2_atom_sequence_clear(LV2_Atom_Sequence* seq)
    LV2_Atom_Event* lv2_atom_sequence_append_event(LV2_Atom_Sequence*    seq,
                                                   uint32_t              capacity,
                                                   const LV2_Atom_Event* event)
    LV2_Atom* lv2_atom_tuple_begin(const LV2_Atom_Tuple* tup)
    bool lv2_atom_tuple_is_end(const void* body, uint32_t size, const LV2_Atom* i)
    LV2_Atom* lv2_atom_tuple_next(const LV2_Atom* i)

    LV2_Atom_Property_Body* lv2_atom_object_begin(const LV2_Atom_Object_Body* body)
    bool lv2_atom_object_is_end(const LV2_Atom_Object_Body*   body,
                                uint32_t                      size,
                                const LV2_Atom_Property_Body* i)
    LV2_Atom_Property_Body* lv2_atom_object_next(const LV2_Atom_Property_Body* i)

    ctypedef struct LV2_Atom_Object_Query:
        uint32_t         key
        const LV2_Atom** value

    int lv2_atom_object_query(const LV2_Atom_Object* object,
                              LV2_Atom_Object_Query* query)
    int lv2_atom_object_body_get(uint32_t size, const LV2_Atom_Object_Body* body, ...)
    int lv2_atom_object_get(const LV2_Atom_Object* object, ...)


cdef extern from "lv2/lv2plug.in/ns/ext/atom/forge.h" nogil:
    # Handle for LV2_Atom_Forge_Sink.
    ctypedef void* LV2_Atom_Forge_Sink_Handle

    # A reference to a chunk of written output.
    ctypedef intptr_t LV2_Atom_Forge_Ref

    # Sink function for writing output.  See lv2_atom_forge_set_sink().
    ctypedef LV2_Atom_Forge_Ref (*LV2_Atom_Forge_Sink)(
        LV2_Atom_Forge_Sink_Handle handle,
        const void*                buf,
        uint32_t                   size)

    # Function for resolving a reference.  See lv2_atom_forge_set_sink().
    ctypedef LV2_Atom* (*LV2_Atom_Forge_Deref_Func)(
        LV2_Atom_Forge_Sink_Handle handle,
        LV2_Atom_Forge_Ref         ref)

    # A stack frame used for keeping track of nested Atom containers.
    cdef struct _LV2_Atom_Forge_Frame:
        _LV2_Atom_Forge_Frame* parent
        LV2_Atom_Forge_Ref     ref
    ctypedef _LV2_Atom_Forge_Frame LV2_Atom_Forge_Frame

    # A "forge" for creating atoms by appending to a buffer.
    ctypedef struct LV2_Atom_Forge:
        uint8_t* buf
        uint32_t offset
        uint32_t size

        LV2_Atom_Forge_Sink        sink
        LV2_Atom_Forge_Deref_Func  deref
        LV2_Atom_Forge_Sink_Handle handle

        LV2_Atom_Forge_Frame* stack

        LV2_URID Blank
        LV2_URID Bool
        LV2_URID Chunk
        LV2_URID Double
        LV2_URID Float
        LV2_URID Int
        LV2_URID Long
        LV2_URID Literal
        LV2_URID Object
        LV2_URID Path
        LV2_URID Property
        LV2_URID Resource
        LV2_URID Sequence
        LV2_URID String
        LV2_URID Tuple
        LV2_URID URI
        LV2_URID URID
        LV2_URID Vector

    void lv2_atom_forge_set_buffer(LV2_Atom_Forge* forge, uint8_t* buf, size_t size)

    # Initialise `forge`.
    #
    # URIs will be mapped using `map` and stored, a reference to `map` itself is
    # not held.
    void lv2_atom_forge_init(LV2_Atom_Forge* forge, LV2_URID_Map* map)

    # Access the Atom pointed to by a reference.
    LV2_Atom* lv2_atom_forge_deref(LV2_Atom_Forge* forge, LV2_Atom_Forge_Ref ref)

    # Push a stack frame.
    # This is done automatically by container functions (which take a stack frame
    # pointer), but may be called by the user to push the top level container when
    # writing to an existing Atom.
    LV2_Atom_Forge_Ref lv2_atom_forge_push(
        LV2_Atom_Forge*       forge,
        LV2_Atom_Forge_Frame* frame,
        LV2_Atom_Forge_Ref    ref)

    # Pop a stack frame.  This must be called when a container is finished.
    void lv2_atom_forge_pop(LV2_Atom_Forge* forge, LV2_Atom_Forge_Frame* frame)

    # Return true iff the top of the stack has the given type.
    bool lv2_atom_forge_top_is(LV2_Atom_Forge* forge, uint32_t type)

    # Return true iff `type` is an atom:Object.
    bool lv2_atom_forge_is_object_type(const LV2_Atom_Forge* forge, uint32_t type)

    # Return true iff `type` is an atom:Object with a blank ID.
    bool lv2_atom_forge_is_blank(
        const LV2_Atom_Forge*       forge,
        uint32_t                    type,
        const LV2_Atom_Object_Body* body)

    # Set the output buffer where `forge` will write atoms.
    void lv2_atom_forge_set_buffer(LV2_Atom_Forge* forge, uint8_t* buf, size_t size)

    # Set the sink function where `forge` will write output.
    #
    # The return value of forge functions is an LV2_Atom_Forge_Ref which is an
    # integer type safe to use as a pointer but is otherwise opaque.  The sink
    # function must return a ref that can be dereferenced to access as least
    # sizeof(LV2_Atom) bytes of the written data, so sizes can be updated.  For
    # ringbuffers, this should be possible as long as the size of the buffer is a
    # multiple of sizeof(LV2_Atom), since atoms are always aligned.
    #
    # Note that 0 is an invalid reference, so if you are using a buffer offset be
    # sure to offset it such that 0 is never a valid reference.  You will get
    # confusing errors otherwise.
    void lv2_atom_forge_set_sink(
        LV2_Atom_Forge*            forge,
        LV2_Atom_Forge_Sink        sink,
        LV2_Atom_Forge_Deref_Func  deref,
        LV2_Atom_Forge_Sink_Handle handle)

    # Write raw output.  This is used internally, but is also useful for writing
    # atom types not explicitly supported by the forge API.  Note the caller is
    # responsible for ensuring the output is approriately padded.
    LV2_Atom_Forge_Ref lv2_atom_forge_raw(LV2_Atom_Forge* forge, const void* data, uint32_t size)

    # Pad output accordingly so next write is 64-bit aligned.
    void lv2_atom_forge_pad(LV2_Atom_Forge* forge, uint32_t written)

    # Write raw output, padding to 64-bits as necessary.
    LV2_Atom_Forge_Ref lv2_atom_forge_write(LV2_Atom_Forge* forge, const void* data, uint32_t size)

    # Write a null-terminated string body.
    LV2_Atom_Forge_Ref lv2_atom_forge_string_body(
        LV2_Atom_Forge* forge,
        const char*     str,
        uint32_t        len)

    # Write an atom:Atom header.
    LV2_Atom_Forge_Ref lv2_atom_forge_atom(LV2_Atom_Forge* forge, uint32_t size, uint32_t type)

    # Write a primitive (fixed-size) atom.
    LV2_Atom_Forge_Ref lv2_atom_forge_primitive(LV2_Atom_Forge* forge, const LV2_Atom* a)

    # Write an atom:Int.
    LV2_Atom_Forge_Ref lv2_atom_forge_int(LV2_Atom_Forge* forge, int32_t val)

    # Write an atom:Long.
    LV2_Atom_Forge_Ref lv2_atom_forge_long(LV2_Atom_Forge* forge, int64_t val)

    # Write an atom:Float.
    LV2_Atom_Forge_Ref lv2_atom_forge_float(LV2_Atom_Forge* forge, float val)

    # Write an atom:Double.
    LV2_Atom_Forge_Ref lv2_atom_forge_double(LV2_Atom_Forge* forge, double val)

    # Write an atom:Bool.
    LV2_Atom_Forge_Ref lv2_atom_forge_bool(LV2_Atom_Forge* forge, bool val)

    # Write an atom:URID.
    LV2_Atom_Forge_Ref lv2_atom_forge_urid(LV2_Atom_Forge* forge, LV2_URID id)

    # Write an atom compatible with atom:String.  Used internally.
    LV2_Atom_Forge_Ref lv2_atom_forge_typed_string(
        LV2_Atom_Forge* forge,
        uint32_t        type,
        const char*     str,
        uint32_t        len)

    # Write an atom:String.  Note that `str` need not be NULL terminated.
    LV2_Atom_Forge_Ref lv2_atom_forge_string(LV2_Atom_Forge* forge, const char* str, uint32_t len)

    # Write an atom:URI.  Note that `uri` need not be NULL terminated.
    # This does not map the URI, but writes the complete URI string.  To write
    # a mapped URI, use lv2_atom_forge_urid().
    LV2_Atom_Forge_Ref lv2_atom_forge_uri(LV2_Atom_Forge* forge, const char* uri, uint32_t len)

    # Write an atom:Path.  Note that `path` need not be NULL terminated.
    LV2_Atom_Forge_Ref lv2_atom_forge_path(LV2_Atom_Forge* forge, const char* path, uint32_t len)

    # Write an atom:Literal.
    LV2_Atom_Forge_Ref lv2_atom_forge_literal(
        LV2_Atom_Forge* forge,
        const char*     str,
        uint32_t        len,
        uint32_t        datatype,
        uint32_t        lang)

    # Start an atom:Vector.
    LV2_Atom_Forge_Ref lv2_atom_forge_vector_head(
        LV2_Atom_Forge*       forge,
        LV2_Atom_Forge_Frame* frame,
        uint32_t              child_size,
        uint32_t              child_type)

    # Write a complete atom:Vector.
    LV2_Atom_Forge_Ref lv2_atom_forge_vector(
        LV2_Atom_Forge* forge,
        uint32_t        child_size,
        uint32_t        child_type,
        uint32_t        n_elems,
        const void*     elems)

    # Write the header of an atom:Tuple.
    #
    # The passed frame will be initialised to represent this tuple.  To complete
    # the tuple, write a sequence of atoms, then pop the frame with
    # lv2_atom_forge_pop().
    #
    # For example:
    # @code
    # // Write tuple (1, 2.0)
    # LV2_Atom_Forge_Frame frame
    # LV2_Atom* tup = (LV2_Atom*)lv2_atom_forge_tuple(forge, &frame)
    # lv2_atom_forge_int32(forge, 1)
    # lv2_atom_forge_float(forge, 2.0)
    # lv2_atom_forge_pop(forge, &frame)
    # @endcode
    LV2_Atom_Forge_Ref lv2_atom_forge_tuple(LV2_Atom_Forge* forge, LV2_Atom_Forge_Frame* frame)

    # Write the header of an atom:Object.
    #
    # The passed frame will be initialised to represent this object.  To complete
    # the object, write a sequence of properties, then pop the frame with
    # lv2_atom_forge_pop().
    #
    # For example:
    # @code
    # LV2_URID eg_Cat  = map("http://example.org/Cat")
    # LV2_URID eg_name = map("http://example.org/name")
    #
    # // Start object with type eg_Cat and blank ID
    # LV2_Atom_Forge_Frame frame
    # lv2_atom_forge_object(forge, &frame, 0, eg_Cat)
    #
    # // Append property eg:name = "Hobbes"
    # lv2_atom_forge_key(forge, eg_name)
    # lv2_atom_forge_string(forge, "Hobbes", strlen("Hobbes"))
    #
    # // Finish object
    # lv2_atom_forge_pop(forge, &frame)
    # @endcode
    LV2_Atom_Forge_Ref lv2_atom_forge_object(
        LV2_Atom_Forge*       forge,
        LV2_Atom_Forge_Frame* frame,
        LV2_URID              id,
        LV2_URID              otype)

    # The same as lv2_atom_forge_object(), but for object:Resource.
    #
    # This function is deprecated and should not be used in new code.
    # Use lv2_atom_forge_object() directly instead.
    LV2_Atom_Forge_Ref lv2_atom_forge_resource(
        LV2_Atom_Forge*       forge,
        LV2_Atom_Forge_Frame* frame,
        LV2_URID              id,
        LV2_URID              otype)

    # The same as lv2_atom_forge_object(), but for object:Blank.
    #
    # This function is deprecated and should not be used in new code.
    # Use lv2_atom_forge_object() directly instead.
    LV2_Atom_Forge_Ref lv2_atom_forge_blank(
        LV2_Atom_Forge*       forge,
        LV2_Atom_Forge_Frame* frame,
        uint32_t              id,
        LV2_URID              otype)

    # Write a property key in an Object, to be followed by the value.
    #
    # See lv2_atom_forge_object() documentation for an example.
    LV2_Atom_Forge_Ref lv2_atom_forge_key(
        LV2_Atom_Forge* forge,
        LV2_URID        key)

    # Write the header for a property body in an object, with context.
    #
    # If you do not need the context, which is almost certainly the case,
    # use the simpler lv2_atom_forge_key() instead.
    LV2_Atom_Forge_Ref lv2_atom_forge_property_head(
        LV2_Atom_Forge* forge,
        LV2_URID        key,
        LV2_URID        context)

    # Write the header for a Sequence.
    LV2_Atom_Forge_Ref lv2_atom_forge_sequence_head(
        LV2_Atom_Forge*       forge,
        LV2_Atom_Forge_Frame* frame,
        uint32_t              unit)

    # Write the time stamp header of an Event (in a Sequence) in audio frames.
    # After this, call the appropriate forge method(s) to write the body.  Note
    # the returned reference is to an LV2_Event which is NOT an Atom.
    LV2_Atom_Forge_Ref lv2_atom_forge_frame_time(LV2_Atom_Forge* forge, int64_t frames)

    # Write the time stamp header of an Event (in a Sequence) in beats.  After
    # this, call the appropriate forge method(s) to write the body.  Note the
    # returned reference is to an LV2_Event which is NOT an Atom.
    LV2_Atom_Forge_Ref lv2_atom_forge_beat_time(LV2_Atom_Forge* forge, double beats)


cdef class Event(object):
    cdef readonly int64_t frames
    cdef readonly Atom atom


cdef class Atom(object):
    cdef LV2_Atom* atom
    cdef PyURIDMapper mapper
    cdef init(self, LV2_Atom* atom)
    @staticmethod
    cdef Atom wrap(PyURIDMapper mapper, uint8_t* buf)


cdef class AtomForge(object):
    cdef LV2_Atom_Forge forge
    cdef URID_Map_Feature map
    cdef LV2_URID midi_event
    cdef LV2_URID frame_time

    cpdef set_buffer(self, uint8_t[:] buf, size_t size)
