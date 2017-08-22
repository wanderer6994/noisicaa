#ifndef _NOISICORE_PROCESSOR_H
#define _NOISICORE_PROCESSOR_H

#include <memory>
#include <string>
#include <stdint.h>

#include "status.h"
#include "buffers.h"
#include "block_context.h"
#include "processor_spec.h"

using std::string;
using std::unique_ptr;

namespace noisicaa {

class Processor {
 public:
  Processor();
  virtual ~Processor();

  static Processor* create(const string& name);

  Status get_string_parameter(const string& name, string* value);

  virtual Status setup(const ProcessorSpec* spec);
  virtual void cleanup();

  virtual Status connect_port(uint32_t port_idx, BufferPtr buf) = 0;
  virtual Status run(BlockContext* ctxt) = 0;

 protected:
  unique_ptr<const ProcessorSpec> _spec;
};

}  // namespace noisicaa

#endif
