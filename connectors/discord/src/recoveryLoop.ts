export interface RecoveryLoopCallbacks {
  execute: () => Promise<void>;
  succeeded: () => Promise<void> | void;
  failed: (error: unknown) => Promise<void> | void;
}

export class RecoveryLoop {
  private timer: NodeJS.Timeout | undefined;
  private running = false;

  constructor(
    private readonly intervalMs: number,
    private readonly callbacks: RecoveryLoopCallbacks
  ) {
    if (!Number.isFinite(intervalMs) || intervalMs < 1) {
      throw new Error("RecoveryLoop intervalMs must be a positive number.");
    }
  }

  start(): void {
    if (this.timer) return;
    void this.runNow();
    this.timer = setInterval(() => {
      void this.runNow();
    }, this.intervalMs);
  }

  async runNow(): Promise<void> {
    if (this.running) return;
    this.running = true;
    try {
      await this.callbacks.execute();
      await this.callbacks.succeeded();
    } catch (error) {
      await this.callbacks.failed(error);
    } finally {
      this.running = false;
    }
  }

  stop(): void {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = undefined;
  }
}
