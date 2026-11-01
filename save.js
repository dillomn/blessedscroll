// Shared "Save" behaviour for BlessedScroll pages.
//
// Over HTTPS on a phone (iPhone especially) we fetch the mp4 from /dl/<id> and
// hand it to the share sheet, which offers "Save Video" straight into Photos.
// iOS only allows share() shortly after a tap, so if the download took too long
// the file is kept and the next tap on Save shares it instantly.
// Anywhere else (desktop, or plain http) the link just downloads the file.
window.BSSave = (() => {
  const isIOS = /iP(hone|ad|od)/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const touch = matchMedia('(pointer: coarse)').matches;
  let canShareFiles = false;
  try {
    canShareFiles = window.isSecureContext && touch && !!navigator.canShare &&
      navigator.canShare({ files: [new File([''], 'x.mp4', { type: 'video/mp4' })] });
  } catch {}

  let ready = null;     // { id, file } downloaded and waiting for a tap
  let busyId = null;

  async function share(file) {
    try {
      await navigator.share({ files: [file] });
      return 'shared';
    } catch (e) {
      if (e && e.name === 'AbortError') return 'cancelled';
      if (e && e.name === 'NotAllowedError') return 'needs-tap';
      throw e;
    }
  }

  /**
   * Click handler for a Save link whose href is /dl/<id>.
   * opts: { id, user, toast(msg, ms), setLabel(text|null) }
   */
  async function onClick(e, { id, user, toast, setLabel }) {
    if (!canShareFiles) {
      if (isIOS && !window.isSecureContext) {
        toast('Downloading to Files. For one-tap Save to Photos, open /setup once to switch to HTTPS.', 5000);
      } else {
        toast('Downloading…', 1800);
      }
      return; // let the link download normally
    }
    e.preventDefault();
    if (ready && ready.id === id) {
      const r = await share(ready.file).catch(() => 'error');
      if (r !== 'needs-tap') { ready = null; setLabel(null); }
      if (r === 'error') toast('Couldn’t open the share sheet');
      return;
    }
    if (busyId === id) return;
    busyId = id;
    setLabel('Saving…');
    try {
      const res = await fetch('/dl/' + id);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const blob = await res.blob();
      const name = `${(user || 'video').replace(/[^\w]/g, '') || 'video'}_${id}.mp4`;
      const file = new File([blob], name, { type: 'video/mp4' });
      const r = await share(file);
      if (r === 'needs-tap') {
        ready = { id, file };
        setLabel('Tap again');
        toast('Video ready — tap Save again to put it in Photos', 4000);
        return;
      }
      setLabel(null);
    } catch (err) {
      console.error(err);
      setLabel(null);
      toast('Couldn’t save that one, try again');
    } finally {
      busyId = null;
    }
  }

  return { onClick, canShareFiles };
})();
