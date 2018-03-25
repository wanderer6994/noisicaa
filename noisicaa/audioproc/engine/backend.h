// -*- mode: c++ -*-

/*
 * @begin:license
 *
 * Copyright (c) 2015-2018, Benjamin Niemann <pink@odahoda.de>
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

#ifndef _NOISICAA_AUDIOPROC_ENGINE_BACKEND_H
#define _NOISICAA_AUDIOPROC_ENGINE_BACKEND_H

#include <mutex>
#include <string>
#include <vector>
#include "noisicaa/core/logging.h"
#include "noisicaa/core/status.h"
#include "noisicaa/audioproc/engine/buffers.h"

namespace noisicaa {

using namespace std;

class BlockContext;
class Realm;
class HostSystem;

struct BackendSettings {
  string datastream_address;
  float time_scale;
};

class Backend {
public:
  virtual ~Backend();

  static StatusOr<Backend*> create(
      HostSystem* host_system, const string& name, const BackendSettings& settings);

  virtual Status setup(Realm* realm);
  virtual void cleanup();

  Status send_message(const string& msg);

  virtual Status begin_block(BlockContext* ctxt) = 0;
  virtual Status end_block(BlockContext* ctxt) = 0;
  virtual Status output(BlockContext* ctxt, const string& channel, BufferPtr samples) = 0;

  void stop() { _stopped = true; }
  bool stopped() const { return _stopped; }

  void release() { _released = true; }
  bool released() const { return _released; }

protected:
  Backend(HostSystem* host_system, const char* logger_name, const BackendSettings& settings);

  HostSystem* _host_system;
  Logger* _logger;
  BackendSettings _settings;
  Realm* _realm = nullptr;
  bool _stopped = false;
  bool _released = false;

  mutex _msg_queue_mutex;
  vector<string> _msg_queue;
};

}  // namespace noisicaa

#endif