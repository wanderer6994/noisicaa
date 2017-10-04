// -*- mode: c++ -*-

/*
 * @begin:license
 *
 * Copyright (c) 2015-2017, Benjamin Niemann <pink@odahoda.de>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 * @end:license
 */

#ifndef _NOISICAA_AUDIOPROC_VM_BUFFERS_H
#define _NOISICAA_AUDIOPROC_VM_BUFFERS_H

#include <memory>
#include <stdint.h>
#include "lv2/lv2plug.in/ns/ext/atom/forge.h"
#include "lv2/lv2plug.in/ns/ext/urid/urid.h"
#include "noisicaa/core/status.h"

namespace noisicaa {

using namespace std;

class HostData;

typedef uint8_t BufferData;
typedef BufferData* BufferPtr;

class BufferType {
public:
  virtual ~BufferType() {}

  virtual uint32_t size(HostData* host_data, uint32_t block_size) const = 0;

  virtual Status clear_buffer(
      HostData* host_data, uint32_t block_size, BufferPtr buf) const = 0;
  virtual Status mix_buffers(
      HostData* host_data, uint32_t block_size, const BufferPtr buf1, BufferPtr buf2) const = 0;
  virtual Status mul_buffer(
      HostData* host_data, uint32_t block_size, BufferPtr buf, float factor) const = 0;
};

class Float : public BufferType {
public:
  uint32_t size(HostData* host_data, uint32_t block_size) const override;

  Status clear_buffer(
      HostData* host_data, uint32_t block_size, BufferPtr buf) const override;
  Status mix_buffers(
      HostData* host_data, uint32_t block_size, const BufferPtr buf1, BufferPtr buf2) const override;
  Status mul_buffer(
      HostData* host_data, uint32_t block_size, BufferPtr buf, float factor) const override;
};

class FloatAudioBlock : public BufferType {
public:
  uint32_t size(HostData* host_data, uint32_t block_size) const override;

  Status clear_buffer(
      HostData* host_data, uint32_t block_size, BufferPtr buf) const override;
  Status mix_buffers(
      HostData* host_data, uint32_t block_size, const BufferPtr buf1, BufferPtr buf2) const override;
  Status mul_buffer(
      HostData* host_data, uint32_t block_size, BufferPtr buf, float factor) const override;
};

class AtomData : public BufferType {
public:
  uint32_t size(HostData* host_data, uint32_t block_size) const override;

  Status clear_buffer(
      HostData* host_data, uint32_t block_size, BufferPtr buf) const override;
  Status mix_buffers(
      HostData* host_data, uint32_t block_size, const BufferPtr buf1, BufferPtr buf2) const override;
  Status mul_buffer(
      HostData* host_data, uint32_t block_size, BufferPtr buf, float factor) const override;
};

class Buffer {
public:
  Buffer(HostData* host_data, const BufferType* type);
  ~Buffer();

  const BufferType* type() const { return _type; }
  BufferPtr data() { return _data.get(); }
  uint32_t size() const { return _size; }

  Status allocate(uint32_t block_size);

  Status clear();
  Status mix(const Buffer* other);
  Status mul(float factor);

private:
  const BufferType* _type;
  HostData* _host_data;

  uint32_t _block_size;
  unique_ptr<uint8_t> _data;
  uint32_t _size;
};

}  // namespace noisicaa

#endif
