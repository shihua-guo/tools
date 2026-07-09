#!/bin/sh
set -u

file="/tmp/openlist-qos-baseline-5m.$$"
sorted="${file}.sorted"
: > "$file"

cleanup() {
	rm -f "$file" "$sorted"
}
trap cleanup EXIT INT TERM

get_bytes() {
	nft list counter inet openlist_qos other_download 2>/dev/null |
		awk '/packets/ {
			for (i = 1; i <= NF; i++) {
				if ($i == "bytes") {
					print $(i + 1)
					exit
				}
			}
		}'
}

start_time="$(date '+%Y-%m-%d %H:%M:%S')"
previous="$(get_bytes)"
[ -n "$previous" ] || {
	echo "counter unavailable"
	exit 1
}

i=1
while [ "$i" -le 60 ]; do
	sleep 5
	current="$(get_bytes)"
	[ -n "$current" ] || current="$previous"
	delta=$((current - previous))
	[ "$delta" -lt 0 ] && delta=0
	rate=$((delta * 8 / 5000))
	echo "$rate" >> "$file"
	previous="$current"
	i=$((i + 1))
done

end_time="$(date '+%Y-%m-%d %H:%M:%S')"
sort -n "$file" > "$sorted"
count="$(wc -l < "$file")"
sum="$(awk '{ sum += $1 } END { print sum + 0 }' "$file")"
average=$((sum / count))
minimum="$(sed -n '1p' "$sorted")"
p50="$(sed -n '30p' "$sorted")"
p90="$(sed -n '54p' "$sorted")"
p95="$(sed -n '57p' "$sorted")"
p99="$(sed -n '60p' "$sorted")"
maximum="$(tail -n 1 "$sorted")"

echo "start=$start_time"
echo "end=$end_time"
echo "samples=$count interval_seconds=5"
echo "min=$minimum avg=$average p50=$p50 p90=$p90 p95=$p95 p99=$p99 max=$maximum"
awk '
	BEGIN { a=b=c=d=e=f=g=0 }
	{
		if ($1 < 16) a++
		if ($1 < 32) b++
		if ($1 < 64) c++
		if ($1 < 128) d++
		if ($1 < 256) e++
		if ($1 < 512) f++
		if ($1 < 1024) g++
	}
	END {
		printf "below_16=%d below_32=%d below_64=%d below_128=%d below_256=%d below_512=%d below_1024=%d\n",
			a,b,c,d,e,f,g
	}
' "$file"
echo "series_kbit_per_s:"
tr '\n' ' ' < "$file"
echo
printf "current_openlist_limit="
cat /var/run/openlist-qos.rate 2>/dev/null || echo inactive
free | sed -n '1,2p'
