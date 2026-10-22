#!/data/data/com.termux/files/usr/bin/bash
set -u
printf 'Modelo: '; getprop ro.product.model
printf 'Android: '; getprop ro.build.version.release
printf 'SDK: '; getprop ro.build.version.sdk
printf 'ABIs: '; getprop ro.product.cpu.abilist
printf 'Maquina: '; uname -m
printf '\nVulkan anunciado pelo Android:\n'
pm list features | grep -i vulkan || true
printf '\nRAM (KB):\n'
grep -E 'MemTotal|MemAvailable' /proc/meminfo || true
printf '\nOBS: "pm list features" nao prova que o renderer Xerenge roda.\n'
