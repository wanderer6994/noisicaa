from libc.stdint cimport uint8_t

from enum import Enum
import itertools
import math
import sys

import numpy
cimport numpy

### DECLARATIONS ##########################################################

cdef extern from "dlfcn.h":
    enum:
        RTLD_LAZY
        RTLD_NOW
        RTLD_GLOBAL
        RTLD_DEFAULT
        RTLD_NEXT
    void *dlopen(char *filename, int flag)
    char *dlerror()
    void *dlsym(void *handle, char *symbol)
    int dlclose(void *handle)

cdef extern from "ladspa.h" nogil:
    ctypedef float LADSPA_Data
    ctypedef void* LADSPA_Handle

    ctypedef int LADSPA_Properties
    enum:
        LADSPA_PROPERTY_REALTIME
        LADSPA_PROPERTY_INPLACE_BROKEN
        LADSPA_PROPERTY_HARD_RT_CAPABLE

    int LADSPA_IS_REALTIME(int)
    int LADSPA_IS_INPLACE_BROKEN(int)
    int LADSPA_IS_HARD_RT_CAPABLE(int)

    ctypedef int LADSPA_PortDescriptor
    enum:
        LADSPA_PORT_INPUT
        LADSPA_PORT_OUTPUT
        LADSPA_PORT_CONTROL
        LADSPA_PORT_AUDIO

    int LADSPA_IS_PORT_INPUT(int)
    int LADSPA_IS_PORT_OUTPUT(int)
    int LADSPA_IS_PORT_CONTROL(int)
    int LADSPA_IS_PORT_AUDIO(int)

    ctypedef int LADSPA_PortRangeHintDescriptor
    enum:
        LADSPA_HINT_BOUNDED_BELOW
        LADSPA_HINT_BOUNDED_ABOVE
        LADSPA_HINT_TOGGLED
        LADSPA_HINT_SAMPLE_RATE
        LADSPA_HINT_LOGARITHMIC
        LADSPA_HINT_INTEGER
        LADSPA_HINT_DEFAULT_MASK
        LADSPA_HINT_DEFAULT_NONE
        LADSPA_HINT_DEFAULT_MINIMUM
        LADSPA_HINT_DEFAULT_LOW
        LADSPA_HINT_DEFAULT_MIDDLE
        LADSPA_HINT_DEFAULT_HIGH
        LADSPA_HINT_DEFAULT_MAXIMUM
        LADSPA_HINT_DEFAULT_0
        LADSPA_HINT_DEFAULT_1
        LADSPA_HINT_DEFAULT_100
        LADSPA_HINT_DEFAULT_440

    int LADSPA_IS_HINT_BOUNDED_BELOW(int)
    int LADSPA_IS_HINT_BOUNDED_ABOVE(int)
    int LADSPA_IS_HINT_TOGGLED(int)
    int LADSPA_IS_HINT_SAMPLE_RATE(int)
    int LADSPA_IS_HINT_LOGARITHMIC(int)
    int LADSPA_IS_HINT_INTEGER(int)
    int LADSPA_IS_HINT_HAS_DEFAULT(int)
    int LADSPA_IS_HINT_DEFAULT_MINIMUM(int)
    int LADSPA_IS_HINT_DEFAULT_LOW(int)
    int LADSPA_IS_HINT_DEFAULT_MIDDLE(int)
    int LADSPA_IS_HINT_DEFAULT_HIGH(int)
    int LADSPA_IS_HINT_DEFAULT_MAXIMUM(int)
    int LADSPA_IS_HINT_DEFAULT_0(int)
    int LADSPA_IS_HINT_DEFAULT_1(int)
    int LADSPA_IS_HINT_DEFAULT_100(int)
    int LADSPA_IS_HINT_DEFAULT_440(int)

    ctypedef struct LADSPA_PortRangeHint:
        LADSPA_PortRangeHintDescriptor HintDescriptor
        LADSPA_Data LowerBound
        LADSPA_Data UpperBound

    ctypedef struct LADSPA_Descriptor:
        unsigned long UniqueID
        char* Label
        LADSPA_Properties Properties
        char* Name
        char* Maker
        char* Copyright
        unsigned long PortCount
        LADSPA_PortDescriptor* PortDescriptors
        char** PortNames
        LADSPA_PortRangeHint* PortRangeHints
        void* ImplementationData
        LADSPA_Handle (*instantiate)(void* descriptor, int sample_rate)
        void (*connect_port)(
            LADSPA_Handle Instance, unsigned long port, LADSPA_Data* data_location)
        void (*activate)(LADSPA_Handle Instance)
        void (*run)(LADSPA_Handle instance, unsigned long sample_count)
        void (*run_adding)(LADSPA_Handle instance, unsigned long sample_count)
        void (*set_run_adding_gain)(LADSPA_Handle instance, LADSPA_Data gain)
        void (*deactivate)(LADSPA_Handle instance)
        void (*cleanup)(LADSPA_Handle instance)

    LADSPA_Descriptor* ladspa_descriptor(unsigned long index)
    ctypedef LADSPA_Descriptor* (*LADSPA_Descriptor_Function)(unsigned long index)


### CLIENT CODE ###########################################################

class Error(Exception):
    pass


class PortDirection(Enum):
    Input = 'input'
    Output = 'output'


class PortType(Enum):
    Control = 'control'
    Audio = 'audio'


cdef class Port(object):
    cdef LADSPA_PortDescriptor _desc
    cdef LADSPA_PortRangeHint _range_hint
    cdef int _index
    cdef const char* _name

    def __str__(self):
        s = '<port "%s" %s %s' % (self.name, self.type.value, self.direction.value)
        if self.is_bounded:
            lower = self.lower_bound(1)
            upper = self.upper_bound(1)
            s += ' ['
            if lower is not None:
                s += str(lower)
            s += ':'
            if upper is not None:
                s += str(upper)
            s += ']'
            if self.is_sample_rate:
                s += '*sr'

        default = self.default(1)
        if default is not None:
            s += ' default=%f' % default

        if self.is_logarithmic:
            s += ' logarithmic'
        s += '>'
        return s

    @property
    def index(self):
        return self._index

    @property
    def name(self):
        return bytes(self._name).decode('ascii')

    @property
    def direction(self):
        if LADSPA_IS_PORT_INPUT(self._desc):
            return PortDirection.Input
        if LADSPA_IS_PORT_OUTPUT(self._desc):
            return PortDirection.Output

    @property
    def type(self):
        if LADSPA_IS_PORT_AUDIO(self._desc):
            return PortType.Audio
        if LADSPA_IS_PORT_CONTROL(self._desc):
            return PortType.Control

    @property
    def is_bounded(self):
        return bool(
            LADSPA_IS_HINT_BOUNDED_BELOW(self._range_hint.HintDescriptor)
            or LADSPA_IS_HINT_BOUNDED_ABOVE(self._range_hint.HintDescriptor))

    def lower_bound(self, sample_rate):
        if LADSPA_IS_HINT_BOUNDED_BELOW(self._range_hint.HintDescriptor):
            if self.is_integer:
                return int(self._range_hint.LowerBound)
            elif self.is_sample_rate:
                return self._range_hint.LowerBound * sample_rate
            else:
                return self._range_hint.LowerBound
        else:
            return None

    def upper_bound(self, sample_rate):
        if LADSPA_IS_HINT_BOUNDED_ABOVE(self._range_hint.HintDescriptor):
            if self.is_integer:
                return int(self._range_hint.UpperBound)
            elif self.is_sample_rate:
                return self._range_hint.UpperBound * sample_rate
            else:
                return self._range_hint.UpperBound
        else:
            return None

    def default(self, sample_rate):
        if LADSPA_IS_HINT_DEFAULT_0(self._range_hint.HintDescriptor):
            return 0.0
        if LADSPA_IS_HINT_DEFAULT_1(self._range_hint.HintDescriptor):
            return 1.0
        if LADSPA_IS_HINT_DEFAULT_100(self._range_hint.HintDescriptor):
            return 100.0
        if LADSPA_IS_HINT_DEFAULT_440(self._range_hint.HintDescriptor):
            return 440.0
        if LADSPA_IS_HINT_DEFAULT_MINIMUM(self._range_hint.HintDescriptor):
            return self.lower_bound(sample_rate)
        if LADSPA_IS_HINT_DEFAULT_MAXIMUM(self._range_hint.HintDescriptor):
            return self.upper_bound(sample_rate)
        if LADSPA_IS_HINT_DEFAULT_LOW(self._range_hint.HintDescriptor):
            return self.weighted_mean(sample_rate, 0.75, 0.25)
        if LADSPA_IS_HINT_DEFAULT_MIDDLE(self._range_hint.HintDescriptor):
            return self.weighted_mean(sample_rate, 0.5, 0.5)
        if LADSPA_IS_HINT_DEFAULT_HIGH(self._range_hint.HintDescriptor):
            return self.weighted_mean(sample_rate, 0.25, 0.75)

        return None

    def weighted_mean(self, sample_rate, w1, w2):
        lower = self.lower_bound(sample_rate)
        if lower is None:
            lower = 0.0
        upper = self.upper_bound(sample_rate)
        if upper is None:
            upper = lower + 1.0
        if self.is_logarithmic:
            try:
                return math.exp(w1 * math.log(lower) + w2 * math.log(upper))
            except ValueError:
                # Crappy plugins might specify a logarithmic port with
                # a lower bound of zero...
                return lower
        else:
            return w1 * lower + w2 * upper

    @property
    def is_sample_rate(self):
        return bool(LADSPA_IS_HINT_SAMPLE_RATE(self._range_hint.HintDescriptor))

    @property
    def is_logarithmic(self):
        return bool(LADSPA_IS_HINT_LOGARITHMIC(self._range_hint.HintDescriptor))

    @property
    def is_integer(self):
        return bool(LADSPA_IS_HINT_INTEGER(self._range_hint.HintDescriptor))


cdef class Instance(object):
    cdef Descriptor _desc
    cdef LADSPA_Handle _handle

    def __dealloc__(self):
        if self._handle != NULL:
            self._desc._desc.cleanup(self._handle)
            self._handle = NULL

    def connect_port(self, port, data):
        cdef void* ptr
        cdef numpy.ndarray[float, ndim=1, mode="c"] arr
        cdef char[:] view
        if data is None:
            ptr = NULL
        elif isinstance(data, numpy.ndarray):
            arr = data
            ptr = &arr[0]
        elif isinstance(data, memoryview):
            view = data
            ptr = &view[0]
        elif isinstance(data, (bytes, bytearray)):
            ptr = <uint8_t*>data
        else:
            raise TypeError(type(data))

        assert self._handle != NULL
        self._desc._desc.connect_port(
            self._handle, port.index, <LADSPA_Data*>ptr)

    def activate(self):
        assert self._handle != NULL
        if self._desc._desc.activate != NULL:
            self._desc._desc.activate(self._handle)

    def run(self, num_samples):
        assert self._handle != NULL
        self._desc._desc.run(self._handle, num_samples)

    def deactivate(self):
        assert self._handle != NULL
        if self._desc._desc.deactivate != NULL:
            self._desc._desc.deactivate(self._handle)

    def cleanup(self):
        if self._handle != NULL:
            self._desc._desc.cleanup(self._handle)
            self._handle = NULL

    def close(self):
        self.cleanup()
        self._desc._instances.remove(self)


cdef class Descriptor(object):
    cdef const LADSPA_Descriptor* _desc
    cdef list _instances
    cdef readonly list ports

    def __init__(self):
        self._instances = []
        self.ports = []

    def __dealloc__(self):
        self.close_all_instances()

    @property
    def id(self):
        return self._desc.UniqueID

    @property
    def label(self):
        return bytes(self._desc.Label).decode('ascii')

    @property
    def name(self):
        return bytes(self._desc.Name).decode('ascii')

    @property
    def maker(self):
        return bytes(self._desc.Maker).decode('ascii')

    @property
    def copyright(self):
        return bytes(self._desc.Copyright).decode('ascii')

    def instantiate(self, unsigned long sample_rate):
        cdef LADSPA_Handle handle

        handle = self._desc.instantiate(self._desc, sample_rate)
        if handle == NULL:
            raise Error
        instance = Instance()
        instance._desc = self
        instance._handle = handle
        self._instances.append(instance)
        return instance

    def close_all_instances(self):
        for instance in self._instances:
            instance.cleanup()
        self._instances.clear()


cdef class Library(object):
    cdef void* handle
    cdef readonly list descriptors

    def __init__(self, path):
        cdef char* error
        cdef LADSPA_Descriptor_Function ladspa_descriptor
        cdef const LADSPA_Descriptor* ld
        cdef object ld_object

        self.descriptors = []

        self.handle = dlopen(path.encode(sys.getfilesystemencoding()), RTLD_NOW)
        if self.handle == NULL:
            raise Error(dlerror().decode('utf-8'))

        ladspa_descriptor = <LADSPA_Descriptor_Function>dlsym(self.handle, "ladspa_descriptor")
        error = dlerror()
        if error != NULL:
            raise Error(unicode(error, 'utf-8'))

        for index in itertools.count(0):
            ld = ladspa_descriptor(index)
            if ld == NULL:
                break

            pd = Descriptor()
            pd._desc = ld
            for pindex in range(ld.PortCount):
                port = Port()
                port._index = pindex
                port._desc = ld.PortDescriptors[pindex]
                port._range_hint = ld.PortRangeHints[pindex]
                port._name = ld.PortNames[pindex]
                pd.ports.append(port)

            self.descriptors.append(pd)

    def __dealloc__(self):
        for descriptor in self.descriptors:
            descriptor.close_all_instances()
        self.descriptors.clear()

        if self.handle != NULL:
            dlclose(self.handle)
            self.handle = NULL

    def get_descriptor(self, label):
        for descriptor in self.descriptors:
            if descriptor.label == label:
                return descriptor
        raise KeyError(label)
