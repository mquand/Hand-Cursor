/**
 * One-Euro Filter (1 € Filter)
 * Designed for filtering noisy signals in real-time human interaction.
 * Balances jitter reduction at low speeds with zero-lag at high speeds.
 * Reference: Casiez, G., Roussel, N. and Vogel, D. (CHI 2012)
 */

class LowPassFilter {
  constructor(alpha = 0.5, initVal = 0) {
    this.alpha = alpha;
    this.s = initVal;
    this.initialized = false;
  }

  filter(value, alpha) {
    if (alpha !== undefined) this.alpha = alpha;
    if (!this.initialized) {
      this.s = value;
      this.initialized = true;
      return value;
    }
    this.s = this.alpha * value + (1.0 - this.alpha) * this.s;
    return this.s;
  }

  hasLastRawValue() {
    return this.initialized;
  }

  lastRawValue() {
    return this.s;
  }

  reset() {
    this.initialized = false;
  }
}

export class OneEuroFilter {
  constructor(minCutoff = 1.0, beta = 0.007, dCutoff = 1.0) {
    this.minCutoff = minCutoff;
    this.beta = beta;
    this.dCutoff = dCutoff;
    this.xFilter = new LowPassFilter();
    this.dxFilter = new LowPassFilter();
    this.lastTimestamp = null;
  }

  alpha(cutoff, dt) {
    const tau = 1.0 / (2.0 * Math.PI * cutoff);
    return 1.0 / (1.0 + tau / dt);
  }

  filter(value, timestamp) {
    if (this.lastTimestamp === null || timestamp === undefined) {
      this.lastTimestamp = timestamp || performance.now();
      return this.xFilter.filter(value);
    }

    const dt = Math.max((timestamp - this.lastTimestamp) / 1000.0, 0.001);
    this.lastTimestamp = timestamp;

    const prevX = this.xFilter.lastRawValue();
    const dx = this.xFilter.hasLastRawValue() ? (value - prevX) / dt : 0;
    const edx = this.dxFilter.filter(dx, this.alpha(this.dCutoff, dt));

    const cutoff = this.minCutoff + this.beta * Math.abs(edx);
    return this.xFilter.filter(value, this.alpha(cutoff, dt));
  }

  reset() {
    this.xFilter.reset();
    this.dxFilter.reset();
    this.lastTimestamp = null;
  }
}

export class Point2DFilter {
  constructor(minCutoff = 1.0, beta = 0.008, dCutoff = 1.0) {
    this.fx = new OneEuroFilter(minCutoff, beta, dCutoff);
    this.fy = new OneEuroFilter(minCutoff, beta, dCutoff);
  }

  setParams(minCutoff, beta) {
    this.fx.minCutoff = minCutoff;
    this.fx.beta = beta;
    this.fy.minCutoff = minCutoff;
    this.fy.beta = beta;
  }

  filter(x, y, timestamp) {
    return {
      x: this.fx.filter(x, timestamp),
      y: this.fy.filter(y, timestamp)
    };
  }

  reset() {
    this.fx.reset();
    this.fy.reset();
  }
}
