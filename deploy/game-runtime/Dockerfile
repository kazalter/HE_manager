# syntax=docker/dockerfile:1
FROM lscr.io/linuxserver/winegui@sha256:11b54e3c42d7b9cef20f22ba7cea4dc9767edca36794515ba766c5395bef8e2d

COPY stream-relay.py /usr/local/bin/he-game-stream-relay
COPY fix-pulse-owner.sh /custom-cont-init.d/99-he-manager-pulse-owner
RUN chmod 0755 /custom-cont-init.d/99-he-manager-pulse-owner

# Debian's Wine 8 is kept alongside WineHQ: this game's PlayDRM launcher
# does not initialize correctly with the newer Wine shipped in the base.
# Bind the verified packages only during the build, so the archives do not
# become an extra layer in the resulting image.
RUN --mount=type=bind,source=debs,target=/tmp/debs,readonly \
    cd /tmp/debs && \
    echo 'b9e73ca486bc2aa66da86b5724220d2dd7c8299636b1df74c3414757a2170615  libz.deb' | sha256sum -c - && \
    echo 'c992aad6a47d81b719514f5d06c5df10267f1e40a6f4f3b4e3f655cbbf308d57  libwine.deb' | sha256sum -c - && \
    echo '8d2ea88c4f45e813401e10f139456098f21a9a68440b36ea0da4644a2cbe21f8  wine32.deb' | sha256sum -c - && \
    dpkg -i --force-depends /tmp/debs/libz.deb /tmp/debs/libwine.deb /tmp/debs/wine32.deb
