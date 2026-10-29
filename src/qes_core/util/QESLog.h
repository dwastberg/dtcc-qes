/****************************************************************************
 * Copyright (c) 2025 University of Utah
 * Copyright (c) 2025 University of Minnesota Duluth
 *
 * Copyright (c) 2025 Behnam Bozorgmehr
 * Copyright (c) 2025 Jeremy A. Gibbs
 * Copyright (c) 2025 Fabien Margairaz
 * Copyright (c) 2025 Eric R. Pardyjak
 * Copyright (c) 2025 Zachary Patterson
 * Copyright (c) 2025 Rob Stoll
 * Copyright (c) 2025 Lucas Ulmer
 * Copyright (c) 2025 Pete Willemsen
 *
 * This file is part of QES-Winds
 *
 * GPL-3.0 License
 *
 * QES-Winds is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, version 3 of the License.
 *
 * QES-Winds is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with QES-Winds. If not, see <https://www.gnu.org/licenses/>.
 ****************************************************************************/

#pragma once
#include <cstdio>
#include <exception>
#include <functional>
#include <sstream>
#include <string>
#include <utility>
#include "QESException.h"

namespace qes::log {
enum class Level { debug, info, warning, error };
using Handler = std::function<void(Level, const std::string &)>;
// Installing handlers and native runs must be serialized by the host.
// An empty handler discards all messages; handlers never call Python natively.
Handler set_handler(Handler) noexcept;
void emit(Level, const std::string &) noexcept;

class ScopedHandler
{
  Handler previous_;
public:
  explicit ScopedHandler(Handler handler) : previous_(set_handler(std::move(handler))) {}
  ~ScopedHandler() noexcept { set_handler(std::move(previous_)); }
  ScopedHandler(const ScopedHandler &) = delete;
  ScopedHandler &operator=(const ScopedHandler &) = delete;
};

class Message : public std::ostringstream
{
  Level level_;
  int uncaught_ = std::uncaught_exceptions();
public:
  explicit Message(Level level) : level_(level) {}
  ~Message() noexcept
  {
    // Logging must neither mask an exception nor throw from destruction.
    try {
      if (std::uncaught_exceptions() == uncaught_)
        emit(level_, str());
    } catch (...) {}
  }
};
inline Message debug() { return Message(Level::debug); }
inline Message info() { return Message(Level::info); }
inline Message warning() { return Message(Level::warning); }
inline Message error() { return Message(Level::error); }

// vsnprintf formats into memory only; no stdio output or descriptor changes.
#if defined(__GNUC__) || defined(__clang__)
__attribute__((format(printf, 2, 3)))
#endif
void writef(Level, const char *format, ...);
}
