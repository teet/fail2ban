# default shell
#   Test script used in fail2ban test suite
#   Author: Serg G. Brester (sebres)
# return code: 
#   0 - if ip should be ignored (10.0.0.1), 1 - otherwise
echo ---test---$1
if [ "$1" = "10.0.0.1" ]; then
  echo ---ignore---
  exit 0
else
  echo ---bad-ip---
  exit 1
fi
