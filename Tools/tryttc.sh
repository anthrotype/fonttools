#!/bin/bash

rm -f /tmp/ttc.*
rm -f /tmp/LobsttcA-TTF*

echo
echo "*** Can we dump individual fonts from /tmp/testdata/LobsttcA-TTF.ttc ***"
for i in 0 1; do
  ./ttx -y $i -e -o /tmp/LobsttcA-TTF.ttc-$i /tmp/testdata/LobsttcA-TTF.ttc || exit 1
done

echo
echo "*** Verify /tmp/testdata/LobsttcA-TTF.ttc ***"
python ./verifylobsttc.py /tmp/testdata/LobsttcA-TTF.ttc || exit 1

echo
echo "*** Create /tmp/ttc.ttx from /tmp/testdata/LobsttcA-TTF.ttc ***"
./ttx -v -e -o /tmp/ttc.ttx /tmp/testdata/LobsttcA-TTF.ttc || exit 1

echo
echo "*** Create /ttc.roundtrip.ttc from /tmp/ttc.ttx ***"
./ttx -v -e -o /tmp/ttc.roundtrip.ttc /tmp/ttc.ttx || exit 1

echo
echo "*** Verify /ttc.roundtrip.ttc ***"
python ./verifylobsttc.py /tmp/ttc.roundtrip.ttc || exit 1

echo
echo "*** Can we dump individual fonts from /tmp/ttc.roundtrip.ttc ***"
for i in 0 1; do
  ./ttx -y $i -v -e -o /tmp/ttc.ttx2-$i /tmp/ttc.roundtrip.ttc || exit 1
done

echo
echo "*** Create /ttc.ttx2 from /tmp/ttc.roundtrip.ttc ***"
./ttx -v -e -o /tmp/ttc.ttx2 /tmp/ttc.roundtrip.ttc || exit 1

echo
echo "*** THE FINAL DIFF THAT PROBABLY ISN'T SUPPOSED TO PASS ***"
diff /tmp/ttc.ttx /tmp/ttc.ttx2 || exit 1
