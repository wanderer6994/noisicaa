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

#include "noisicaa/audioproc/engine/misc.h"
#include "noisicaa/audioproc/engine/processor_sample_player.h"

namespace noisicaa {

ProcessorSamplePlayer::ProcessorSamplePlayer(
    const string& node_id, HostSystem *host_system, const pb::NodeDescription& desc)
  : ProcessorCSoundBase(
        node_id, "noisicaa.audioproc.engine.processor.sample_player", host_system, desc) {}

Status ProcessorSamplePlayer::setup_internal() {
  RETURN_IF_ERROR(ProcessorCSoundBase::setup_internal());

  if (!_desc.has_sample_player()) {
    return ERROR_STATUS("NodeDescription misses sample_player field.");
  }

  // TODO:
  // - get sample attributes using sndfile
  // - explicitly set table size, so loading is not deferred.
  string orchestra = R"---(
0dbfs = 1.0
ksmps = 32
nchnls = 2
gaOutL chnexport "out:left", 2
gaOutR chnexport "out:right", 2
instr 1
  iPitch = p4
  iVelocity = p5
  iFreq = cpsmidinn(iPitch)
  if (iVelocity == 0) then
    iAmp = 0.0
  else
    iAmp = 0.5 * db(-20 * log10(127^2 / iVelocity^2))
  endif
  iChannels = ftchnls(1)
  if (iChannels == 1) then
    aOut loscil3 iAmp, iFreq, 1, 261.626, 0
    gaOutL = gaOutL + aOut
    gaOutR = gaOutR + aOut
  elseif (iChannels == 2) then
    aOutL, aOutR loscil3 iAmp, iFreq, 1, 220, 0
    gaOutL = gaOutL + aOutL
    gaOutR = gaOutR + aOutR
  endif
endin
)---";

  string score = sprintf("f 1 0 0 -1 \"%s\" 0 0 0\n", _desc.sample_player().sample_path().c_str());

  // first note will fail, because ftable is not yet loaded.
  // play a silent note to trigger ftable initialization.
  score += "i 1 0 0.01 40 0\n";

  RETURN_IF_ERROR(set_code(orchestra, score));

  return Status::Ok();
}

void ProcessorSamplePlayer::cleanup_internal() {
  ProcessorCSoundBase::cleanup_internal();
}

}