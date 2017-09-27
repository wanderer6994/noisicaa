#include <stdlib.h>
#include "capnp/pretty-print.h"
#include "capnp/serialize.h"
#include "noisicaa/core/message.capnp.h"
#include "noisicaa/audioproc/vm/opcodes.h"
#include "noisicaa/audioproc/vm/host_data.h"
#include "noisicaa/audioproc/vm/backend.h"
#include "noisicaa/audioproc/vm/vm.h"

namespace noisicaa {

Status run_END(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  state->end = true;
  return Status::Ok();
}

Status run_COPY(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx1 = args[0].int_value();
  int idx2 = args[1].int_value();
  Buffer* buf1 = state->program->buffers[idx1].get();
  Buffer* buf2 = state->program->buffers[idx2].get();
  assert(buf1->size() == buf2->size());
  memmove(buf2->data(), buf1->data(), buf2->size());
  return Status::Ok();
}

Status run_CLEAR(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx = args[0].int_value();
  Buffer* buf = state->program->buffers[idx].get();
  buf->clear();
  return Status::Ok();
}

Status run_MIX(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx1 = args[0].int_value();
  int idx2 = args[1].int_value();
  Buffer* buf1 = state->program->buffers[idx1].get();
  Buffer* buf2 = state->program->buffers[idx2].get();
  buf2->mix(buf1);
  return Status::Ok();
}

Status run_MUL(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx = args[0].int_value();
  float factor = args[1].float_value();
  Buffer* buf = state->program->buffers[idx].get();
  buf->mul(factor);
  return Status::Ok();
}

Status run_SET_FLOAT(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx = args[0].int_value();
  float value = args[1].float_value();
  Buffer* buf = state->program->buffers[idx].get();
  float* data = (float*)buf->data();
  *data = value;
  return Status::Ok();
}

Status run_OUTPUT(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx = args[0].int_value();
  string channel = args[1].string_value();
  Buffer* buf = state->program->buffers[idx].get();

  return state->backend->output(ctxt, channel, buf->data());
}

Status run_FETCH_BUFFER(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  string in_buf_name = args[0].string_value();
  int out_buf_idx = args[1].int_value();

  Buffer* out_buf = state->program->buffers[out_buf_idx].get();

  const auto& it = ctxt->buffers.find(in_buf_name);
  if (it == ctxt->buffers.end()) {
    out_buf->clear();
    return Status::Ok();
  }
  const BlockContext::Buffer& in_buf = it->second;

  assert(in_buf.size == out_buf->size());
  memmove(out_buf->data(), in_buf.data, in_buf.size);

  return Status::Ok();
}

Status run_FETCH_MESSAGES(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  string labelset_bytes = args[0].string_value();
  int buf_idx = args[1].int_value();

  kj::ArrayPtr<::capnp::word> words(
      (::capnp::word*)labelset_bytes.c_str(),
      labelset_bytes.size() / sizeof(::capnp::word));
  ::capnp::FlatArrayMessageReader message_reader(words);
  capnp::Labelset::Reader labelset(message_reader.getRoot<capnp::Labelset>());

  Buffer* buf = state->program->buffers[buf_idx].get();

  LV2_Atom_Forge forge;
  lv2_atom_forge_init(&forge, &state->host_data->lv2->urid_map);

  LV2_Atom_Forge_Frame frame;
  lv2_atom_forge_set_buffer(&forge, buf->data(), buf->size());

  lv2_atom_forge_sequence_head(&forge, &frame, state->host_data->lv2->urid.atom_frame_time);

  for (const auto& msg : ctxt->messages) {
    if (msg.getType() != capnp::Type::ATOM) {
      continue;
    }

    // All labels in labelset must match some label in msg.labelset.
    bool matched = false;
    for (const auto& label_a : labelset.getLabels()) {
      matched = false;
      for (const auto& label_b : msg.getLabelset().getLabels()) {
	if (label_b.getKey() == label_a.getKey() && label_b.getValue() == label_a.getValue()) {
	  matched = true;
	  break;
	}
      }

      if (!matched) {
	break;
      }
    }

    if (!matched) {
      continue;
    }

    lv2_atom_forge_frame_time(&forge, 0);
    ::capnp::Data::Reader data = msg.getData();
    lv2_atom_forge_write(&forge, data.begin(), data.size());
  }

  lv2_atom_forge_pop(&forge, &frame);
  // TODO: clear remainder of buf.

  return Status::Ok();
}

Status run_FETCH_CONTROL_VALUE(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  // string name = args[0].string_value();
  // int idx = args[1].int_value();
  // Buffer* buf = state->program->buffers[idx].get();

  //StatusOr<ControlValue> stor_cv = ...
  // def op_FETCH_PARAMETER(self, ctxt, state, *, parameter_idx, buf_idx):
    //     #parameter_name = self.__parameters[parameter_idx]
    //     cdef buffers.Buffer buf = self.__buffers[buf_idx]
    //     buf.clear()
  return Status::Error("FETCH_CONTROL_VALUE not implemented yet.");
}

Status run_NOISE(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx = args[0].int_value();
  Buffer* buf = state->program->buffers[idx].get();

  float* data = (float*)buf->data();
  for (uint32_t i = 0 ; i < ctxt->block_size ; ++i) {
    *data++ = 2.0 * drand48() - 1.0;
  }
  return Status::Ok();
}

Status run_MIDI_MONKEY(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx = args[0].int_value();
  float prob = args[1].float_value();
  Buffer* buf = state->program->buffers[idx].get();

  LV2_Atom_Forge forge;
  lv2_atom_forge_init(&forge, &state->host_data->lv2->urid_map);

  LV2_Atom_Forge_Frame frame;
  lv2_atom_forge_set_buffer(&forge, buf->data(), buf->size());

  lv2_atom_forge_sequence_head(&forge, &frame, state->host_data->lv2->urid.atom_frame_time);
  if (drand48() < prob) {
    uint8_t msg[3] = { 0x90, 62, 100 };
    lv2_atom_forge_frame_time(&forge, random() % ctxt->block_size);
    lv2_atom_forge_atom(&forge, 3, state->host_data->lv2->urid.midi_event);
    lv2_atom_forge_write(&forge, msg, 3);
  }
  lv2_atom_forge_pop(&forge, &frame);

  return Status::Ok();
}

Status run_SINE(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
    // def op_SINE(self, ctxt, state, *, buf_idx, freq):
    //     cdef buffers.Buffer buf = self.__buffers[buf_idx]
    //     assert isinstance(buf.type, buffers.FloatArray), str(buf.type)
    //     cdef float* view = <float*>buf.data

    //     p = state.get('p', 0.0)
    //     for i in range(buf.type.size):
    //         view[i] = math.sin(p)
    //         p += 2 * math.pi * freq / self.__sample_rate
    //         if p > 2 * math.pi:
    //             p -= 2 * math.pi
    //     state['p'] = p
  return Status::Error("SINE not implemented yet.");
}

Status init_CONNECT_PORT(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int processor_idx = args[0].int_value();
  int port_idx = args[1].int_value();
  int buf_idx = args[2].int_value();
  Processor* processor = state->program->spec->get_processor(processor_idx);
  Buffer* buf = state->program->buffers[buf_idx].get();
  return processor->connect_port(port_idx, buf->data());
}

Status run_CALL(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int processor_idx = args[0].int_value();
  Processor* processor = state->program->spec->get_processor(processor_idx);
  return processor->run(ctxt);
}

Status run_LOG_RMS(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx = args[0].int_value();
  Buffer* buf = state->program->buffers[idx].get();

  float* data = (float*)buf->data();
  float sum = 0.0;
  for (uint32_t i = 0 ; i < ctxt->block_size ; ++i) {
    sum += data[i] * data[i];
  }

  state->logger->info("Block %d, rms=%.3f", idx, sum / ctxt->block_size);

  return Status::Ok();
}

Status run_LOG_ATOM(BlockContext* ctxt, ProgramState* state, const vector<OpArg>& args) {
  int idx = args[0].int_value();
  Buffer* buf = state->program->buffers[idx].get();

  LV2_Atom_Sequence* seq = (LV2_Atom_Sequence*)buf->data();
  if (seq->atom.type != state->host_data->lv2->urid.atom_sequence) {
    return Status::Error(
	"Buffer %d: Excepted sequence (%d), got %d.",
	idx, state->host_data->lv2->urid.atom_sequence, seq->atom.type);
  }
  LV2_Atom_Event* event = lv2_atom_sequence_begin(&seq->body);

  while (!lv2_atom_sequence_is_end(&seq->body, seq->atom.size, event)) {
    state->logger->info("Buffer %d, event %d @%d", idx, event->body.type, event->time.frames);
    event = lv2_atom_sequence_next(event);
  }

  return Status::Ok();
}

struct OpSpec opspecs[NUM_OPCODES] = {
  // control flow
  { OpCode::NOOP, "NOOP", "", nullptr, nullptr },
  { OpCode::END, "END", "", nullptr, run_END },

  // buffer access
  { OpCode::COPY, "COPY", "bb", nullptr, run_COPY },
  { OpCode::CLEAR, "CLEAR", "b", nullptr, run_CLEAR },
  { OpCode::MIX, "MIX", "bb", nullptr, run_MIX },
  { OpCode::MUL, "MUL", "bf", nullptr, run_MUL },
  { OpCode::SET_FLOAT, "SET_FLOAT", "bf", nullptr, run_SET_FLOAT },

  // I/O
  { OpCode::OUTPUT, "OUTPUT", "bs", nullptr, run_OUTPUT },
  { OpCode::FETCH_BUFFER, "FETCH_BUFFER", "sb", nullptr, run_FETCH_BUFFER },
  { OpCode::FETCH_MESSAGES, "FETCH_MESSAGES", "sb", nullptr, run_FETCH_MESSAGES },
  { OpCode::FETCH_CONTROL_VALUE, "FETCH_CONTROL_VALUE", "sb", nullptr, run_FETCH_CONTROL_VALUE },

  // generators
  { OpCode::NOISE, "NOISE", "b", nullptr, run_NOISE },
  { OpCode::SINE, "SINE", "bf", nullptr, run_SINE },
  { OpCode::MIDI_MONKEY, "MIDI_MONKEY", "bf", nullptr, run_MIDI_MONKEY },

  // processors
  { OpCode::CONNECT_PORT, "CONNECT_PORT", "pib", init_CONNECT_PORT, nullptr },
  { OpCode::CALL, "CALL", "p", nullptr, run_CALL },

  // processors
  { OpCode::LOG_RMS, "LOG_RMS", "b", nullptr, run_LOG_RMS },
  { OpCode::LOG_ATOM, "LOG_ATOM", "b", nullptr, run_LOG_ATOM },
};

}  // namespace noisicaa