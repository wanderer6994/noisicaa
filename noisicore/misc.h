// -*- mode: c++ -*-

#ifndef _NOISICORE_MISC_H
#define _NOISICORE_MISC_H

#include <string>

namespace noisicaa {

using namespace std;

string sprintf(const string& fmt, ...);

struct ScopeGuardBase {
  ScopeGuardBase() : _active(true) {}

  ScopeGuardBase(ScopeGuardBase&& rhs) : _active(rhs._active) {
    rhs.dismiss();
  }

  void dismiss() { _active = false; }

protected:
  ~ScopeGuardBase() = default;
  bool _active;
};

template<class F> struct ScopeGuard: public ScopeGuardBase {
  ScopeGuard() = delete;
  ScopeGuard(const ScopeGuard&) = delete;

  ScopeGuard(F f)
    : ScopeGuardBase(),
      _f(move(f)) {}

  ScopeGuard(ScopeGuard&& rhs)
    : ScopeGuardBase(move(rhs)),
      _f(move(rhs._f)) {}

  ~ScopeGuard() {
    if (_active) {
      _f();
    }
  }

  ScopeGuard& operator=(const ScopeGuard&) = delete;

private:
  F _f;
};

template<class F> ScopeGuard<F> scopeGuard(F f) {
  return ScopeGuard<F>(move(f));
}

}  // namespace noisicaa

#endif
