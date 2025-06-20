#!/system/bin/sh
lftp -u amantya,root123 10.10.34.237 -e 'cd recording; put /storage/emulated/0/FTP_files/tasty.py; bye'
