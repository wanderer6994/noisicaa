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

#include <functional>
#include "noisicaa/core/logging.h"
#include "noisicaa/audioproc/public/time_mapper.h"
#include "noisicaa/audioproc/public/player_state.pb.h"
#include "noisicaa/audioproc/engine/block_context.h"
#include "noisicaa/audioproc/engine/misc.h"
#include "noisicaa/host_system/host_system.h"
#include "noisicaa/audioproc/engine/double_buffered_state_manager.inl.h"
#include "noisicaa/audioproc/engine/pump.inl.h"
#include "noisicaa/audioproc/engine/player.h"

namespace noisicaa {

PlayerStatePump::PlayerStatePump(
    Logger* logger, void (*callback)(void*, const string&), void* userdata)
  : Pump<PlayerState>(logger, bind(&PlayerStatePump::proxy_callback, this, placeholders::_1)),
    _callback(callback),
    _userdata(userdata) {}

void PlayerStatePump::proxy_callback(const PlayerState& state) {
  pb::PlayerState state_pb;
  state_pb.set_playing(state.playing);
  state.current_time.set_proto(state_pb.mutable_current_time());
  state_pb.set_loop_enabled(state.loop_enabled);
  state.loop_start_time.set_proto(state_pb.mutable_loop_start_time());
  state.loop_end_time.set_proto(state_pb.mutable_loop_end_time());
  string state_serialized;
  assert(state_pb.SerializeToString(&state_serialized));
  _callback(_userdata, state_serialized);
}

string PlayerStateMutation::to_string() const {
  string s = "PlayerStateMutation(";
  bool first = true;
  if (set_playing) {
    if (!first) {
      s += ", ";
    }
    first = false;
    s += sprintf("playing=%d", playing);
  }
  if (set_current_time) {
    if (!first) {
      s += ", ";
    }
    first = false;
    s += sprintf("current_time=%f", current_time.to_float());
  }
  if (set_loop_enabled) {
    if (!first) {
      s += ", ";
    }
    first = false;
    s += sprintf("loop_enabled=%d", loop_enabled);
  }
  if (set_loop_start_time) {
    if (!first) {
      s += ", ";
    }
    first = false;
    s += sprintf("loop_start_time=%f", loop_start_time.to_float());
  }
  if (set_loop_end_time) {
    if (!first) {
      s += ", ";
    }
    first = false;
    s += sprintf("loop_end_time=%f", loop_end_time.to_float());
  }
  s += ")";
  return s;
}

Player::Player(
    HostSystem* host_system, void (*state_callback)(void*, const string&), void* userdata)
  : _logger(LoggerRegistry::get_logger("noisicaa.audioproc.engine.player")),
    _host_system(host_system),
    _state_pump(_logger, state_callback, userdata) {}

Player::~Player() {
  cleanup();
}

Status Player::setup() {
  _logger->info("Setting up player...");
  RETURN_IF_ERROR(_state_pump.setup());
  return Status::Ok();
}

void Player::cleanup() {
  _state_pump.cleanup();
  _logger->info("Player cleaned up.");
}

void Player::update_state(const string& state_serialized) {
  pb::PlayerState state_pb;
  assert(state_pb.ParseFromString(state_serialized));

  PlayerStateMutation mutation;

  mutation.set_playing = state_pb.has_playing();
  if (mutation.set_playing) {
    mutation.playing = state_pb.playing();
  }

  mutation.set_current_time = state_pb.has_current_time();
  if (mutation.set_current_time) {
    mutation.current_time = MusicalTime(state_pb.current_time());
  }

  mutation.set_loop_enabled = state_pb.has_loop_enabled();
  if (mutation.set_loop_enabled) {
    mutation.loop_enabled = state_pb.loop_enabled();
  }

  mutation.set_loop_start_time = state_pb.has_loop_start_time();
  if (mutation.set_loop_start_time) {
    mutation.loop_start_time = MusicalTime(state_pb.loop_start_time());
  }

  mutation.set_loop_end_time = state_pb.has_loop_end_time();
  if (mutation.set_loop_end_time) {
    mutation.loop_end_time = MusicalTime(state_pb.loop_end_time());
  }

  _mutation_queue.push(mutation);
}

void Player::fill_time_map(TimeMapper* time_mapper, BlockContext* ctxt) {
  PlayerStateMutation mutation;
  while (_mutation_queue.pop(mutation)) {
    if (mutation.set_playing) {
      _state.playing = mutation.playing;
    }
    if (mutation.set_current_time) {
      _state.current_time = mutation.current_time;
      _tmap_it = time_mapper->find(_state.current_time);
    }
    if (mutation.set_loop_enabled) {
      _state.loop_enabled = mutation.loop_enabled;
    }
    if (mutation.set_loop_start_time) {
      _state.loop_start_time = mutation.loop_start_time;
    }
    if (mutation.set_loop_end_time) {
      _state.loop_end_time = mutation.loop_end_time;
    }
  }

  ctxt->time_map.resize(_host_system->block_size());
  uint32_t i = 0;

  if (_state.playing) {
    if (!_tmap_it.valid() || !_tmap_it.is_owned_by(time_mapper) ) {
      _tmap_it = time_mapper->find(_state.current_time);
    }

    MusicalTime loop_start_time =
      (_state.loop_enabled && _state.loop_start_time >= MusicalTime(0, 1))
      ? _state.loop_start_time : MusicalTime(0, 1);
    MusicalTime loop_end_time =
      (_state.loop_enabled && _state.loop_end_time >= MusicalTime(0, 1))
      ? _state.loop_end_time : time_mapper->end_time();

    for (auto& stime : ctxt->time_map) {
      if (_state.current_time >= loop_end_time) {
        if (!_state.loop_enabled) {
          _state.current_time = loop_end_time;
          _state.playing = false;
          break;
        } else {
          _state.current_time = loop_start_time;
        }
        _tmap_it = time_mapper->find(_state.current_time);
      }

      MusicalTime prev_time = _state.current_time;
      ++_tmap_it;
      _state.current_time = min(*_tmap_it, loop_end_time);
      assert(_state.current_time > prev_time);

      stime = SampleTime{ prev_time, _state.current_time };

      ++i;
    }

    if (!_state.playing) {
      _logger->info("Playback stopped.");
    }
  }

  while (i < _host_system->block_size()) {
    ctxt->time_map[i] = SampleTime{ MusicalTime(-1, 1), MusicalTime(0, 1) };
    ++i;
  }

  _state_pump.push(_state);
}

}  // namespace noisicaa