#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#define IS_ENABLED(config_macro) (config_macro)

/* Visual Studio 2013's C runtime predates the standard snprintf name. */
#if defined(_MSC_VER) && _MSC_VER < 1900
#define snprintf _snprintf
#endif
