#ifndef TOUCAN_WIDGET_SIMULATOR_LV_CONF_H
#define TOUCAN_WIDGET_SIMULATOR_LV_CONF_H

#include <stdint.h>

#define LV_COLOR_DEPTH 1
#define LV_COLOR_16_SWAP 0

#define LV_MEM_CUSTOM 0
#define LV_MEM_SIZE (128U * 1024U)

#define LV_TICK_CUSTOM 1
#define LV_TICK_CUSTOM_INCLUDE <stdint.h>
#define LV_TICK_CUSTOM_SYS_TIME_EXPR (0U)

#define LV_USE_LOG 0
#define LV_USE_ASSERT_NULL 1

#define LV_USE_CANVAS 1
#define LV_USE_IMG 1
#define LV_USE_LABEL 1

#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_DEFAULT &lv_font_montserrat_14

#define LV_BUILD_EXAMPLES 0
#define LV_BUILD_DEMOS 0

#endif
