// Application-level PlayerSession: coordinates video and audio media playback.
// Guarantees at most one active playback session across the entire desktop application.

class PlayerSession {
  constructor({ embeddedPlayer, getWindow = () => null, onBeforeVideoOpen = () => {} }) {
    if (!embeddedPlayer) throw new Error('EmbeddedPlayer instance is required for PlayerSession');
    this.embeddedPlayer = embeddedPlayer;
    this.getWindow = getWindow;
    this.onBeforeVideoOpen = onBeforeVideoOpen;
    this.activeKind = 'none'; // 'none' | 'video' | 'audio'
    this.activeMedia = null;
    this.listeners = new Set();
  }

  // Delegate embeddedPlayer properties for backward compatibility
  get native() { return this.embeddedPlayer.native; }
  get owner() { return this.embeddedPlayer.owner; }
  get addon() { return this.embeddedPlayer.addon; }
  get library() { return this.embeddedPlayer.library; }
  get size() { return this.embeddedPlayer.size; }
  get references() { return this.embeddedPlayer.references; }
  get receiverReady() { return this.embeddedPlayer.receiverReady; }
  set receiverReady(value) { this.embeddedPlayer.receiverReady = value; }
  get volume() { return this.embeddedPlayer.volume; }
  set volume(value) { this.embeddedPlayer.volume = value; }

  available() { return this.embeddedPlayer.available(); }
  ready() { return this.embeddedPlayer.ready(); }
  resize(value) { return this.embeddedPlayer.resize(value); }
  setMode(mode) { return this.embeddedPlayer.setMode(mode); }
  wait(test, label, timeout) { return this.embeddedPlayer.wait(test, label, timeout); }

  get state() {
    const playerState = this.embeddedPlayer.state;
    return {
      ...playerState,
      sessionKind: this.activeKind,
      sessionMedia: this.activeMedia ? { ...this.activeMedia } : null,
    };
  }

  notifySession() {
    const snapshot = this.sessionState();
    const window = this.getWindow();
    if (window && !window.isDestroyed()) {
      window.webContents.send('he:player-session-changed', snapshot);
    }
    for (const listener of this.listeners) {
      try { listener(snapshot); } catch { /* ignore listener failures */ }
    }
  }

  sessionState() {
    return {
      activeKind: this.activeKind,
      activeMedia: this.activeMedia ? { ...this.activeMedia } : null,
      videoRunning: this.embeddedPlayer.state.running,
      videoPaused: this.embeddedPlayer.state.paused,
      videoPosition: this.embeddedPlayer.state.position,
      videoDuration: this.embeddedPlayer.state.duration,
      videoDroppedFrames: this.embeddedPlayer.state.droppedFrames || 0,
    };
  }

  onSessionChange(callback) {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  }

  async openVideo(unused, source, mode, start = 0, title = '') {
    try { this.onBeforeVideoOpen(); } catch {}
    // Mutual exclusion: stop any active audio session when entering video
    if (this.activeKind === 'audio') {
      this.activeKind = 'none';
      this.activeMedia = null;
    }
    this.activeKind = 'video';
    this.activeMedia = {
      type: 'video',
      url: source?.url || '',
      title: title || '',
      start: Number(start) || 0,
      openedAt: Date.now(),
    };
    try {
      const state = await this.embeddedPlayer.open(unused, source, mode, start, title);
      this.notifySession();
      return {
        ...state,
        sessionKind: this.activeKind,
        sessionMedia: this.activeMedia ? { ...this.activeMedia } : null,
      };
    } catch (error) {
      this.activeKind = 'none';
      this.activeMedia = null;
      this.notifySession();
      throw error;
    }
  }

  async controlVideo(action, value) {
    const state = await this.embeddedPlayer.control(action, value);
    this.notifySession();
    return {
      ...state,
      sessionKind: this.activeKind,
      sessionMedia: this.activeMedia ? { ...this.activeMedia } : null,
    };
  }

  async stopVideo(generation) {
    await this.embeddedPlayer.stop(generation);
    if (this.activeKind === 'video') {
      this.activeKind = 'none';
      this.activeMedia = null;
    }
    this.notifySession();
  }

  open(...args) { return this.openVideo(...args); }
  control(...args) { return this.controlVideo(...args); }
  stop(...args) { return this.stopVideo(...args); }

  beginAudio({ mediaId, title, url, trackIndex = 1 } = {}) {
    // If video was running, stopping it releases native texture leases
    let videoStopPromise = Promise.resolve();
    if (this.activeKind === 'video' || this.embeddedPlayer.state.running) {
      videoStopPromise = this.embeddedPlayer.stop();
    }
    this.activeKind = 'audio';
    this.activeMedia = {
      type: 'audio',
      id: mediaId,
      title: title || '',
      url: url || '',
      trackIndex,
      openedAt: Date.now(),
    };
    this.notifySession();
    return videoStopPromise;
  }

  stopAudio() {
    if (this.activeKind === 'audio') {
      this.activeKind = 'none';
      this.activeMedia = null;
      this.notifySession();
    }
  }

  async stopAll() {
    const videoStop = this.embeddedPlayer.stop();
    this.activeKind = 'none';
    this.activeMedia = null;
    this.notifySession();
    await videoStop;
  }
}

module.exports = { PlayerSession };
