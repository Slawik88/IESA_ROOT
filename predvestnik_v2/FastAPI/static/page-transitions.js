// A cross-document transition can be cancelled when its destination does not opt in.
// Observe its visual promises on both pages before pagereveal; navigation itself succeeds.
(() => {
  // Some WebViews report a skipped cross-document transition without exposing it on pagereveal.
  window.isCancelledPageTransition = error => error?.name === 'InvalidStateError'
    && typeof error.message === 'string'
    && /^Transition was aborted\b/.test(error.message)
    && /\bViewTransition opt-in disabled\b/.test(error.message);
  for (const name of ['pageswap', 'pagereveal']) {
    addEventListener(name, event => {
      const transition = event.viewTransition;
      if (!transition) return;
      for (const promise of [transition.ready, transition.finished, transition.updateCallbackDone]) {
        promise?.catch(() => {});
      }
    });
  }
})();
