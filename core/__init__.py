# Return code severity levels (The-Forge convention)
RET_SUCCESS  = 0x00
RET_WARNING  = 0x02  # e.g. screenshot minor diff
RET_TIMEOUT  = 0x10
RET_CRITICAL = 0xFF  # crash, major regression, memory leak
