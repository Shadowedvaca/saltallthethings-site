/* ============================================
   Show Engine
   Generates and manages weekly show slots
   ============================================ */

const ShowEngine = {
  // First recording date
  FIRST_RECORD_DATE: new Date('2026-01-20T00:00:00'),
  // Launch day - first 4 episodes all release here
  LAUNCH_DATE: new Date('2026-03-03T00:00:00'),
  // Banked episodes released per Tuesday during rollout (1-4)
  ROLLOUT_EPISODES_PER_WEEK: 2,
  // How far out to generate (in months)
  GENERATE_MONTHS_AHEAD: 3,

  /**
   * Initialize or refresh show slots.
   * Ensures slots exist from start date through 3 months from today.
   */
  ensureSlots() {
    let slots = Storage.getShowSlots();
    const target = this._getTargetDate();

    // If no slots exist, generate from scratch
    if (slots.length === 0) {
      slots = this._generateSlots(this.FIRST_RECORD_DATE, target);
      Storage.saveShowSlots(slots);
      return slots;
    }

    // Check if we need to extend
    const lastSlot = slots[slots.length - 1];
    const lastRecordDate = new Date(lastSlot.recordDate);

    if (lastRecordDate < target) {
      // Generate additional slots from the week after the last slot
      const nextDate = new Date(lastRecordDate);
      nextDate.setDate(nextDate.getDate() + 7);
      const newSlots = this._generateSlots(nextDate, target, slots.length + 1);
      slots = slots.concat(newSlots);
      Storage.saveShowSlots(slots);
    }

    return slots;
  },

  /**
   * Get target date (3 months from today)
   */
  _getTargetDate() {
    const target = new Date();
    target.setMonth(target.getMonth() + this.GENERATE_MONTHS_AHEAD);
    return target;
  },

  /**
   * Generate show slots between two dates.
   * @param {Date} startDate - First Tuesday to generate
   * @param {Date} endDate - Generate through this date
   * @param {number} startEpNum - Starting episode number (1-based)
   */
  _generateSlots(startDate, endDate, startEpNum = 1) {
    const slots = [];
    const current = new Date(startDate);
    let epNum = startEpNum;

    while (current <= endDate) {
      const recordDate = new Date(current);
      const releaseDate = this._calculateReleaseDate(recordDate, epNum);

      slots.push({
        id: `slot_${epNum}`,
        episodeNumber: this._formatEpNumber(epNum),
        episodeNum: epNum,
        recordDate: recordDate.toISOString().split('T')[0],
        releaseDate: releaseDate.toISOString().split('T')[0],
        isRollout: this._isRolloutEpisode(recordDate)
      });

      epNum++;
      current.setDate(current.getDate() + 7);
    }

    return slots;
  },

  /**
   * Calculate release date based on episode number.
   * EP001-EP004: All release on launch day (2/17/26)
   * EP005+: Release the Tuesday after recording
   */
  _calculateReleaseDate(recordDate, epNum) {
    const normalRelease = new Date(recordDate);
    normalRelease.setDate(normalRelease.getDate() + 7);

    // If normal release is after launch, this isn't a banked episode
    if (normalRelease > this.LAUNCH_DATE) {
      return normalRelease;
    }

    // Banked episode — spread across Tuesdays at the rollout rate
    const weekOffset = Math.floor((epNum - 1) / this.ROLLOUT_EPISODES_PER_WEEK);
    const release = new Date(this.LAUNCH_DATE);
    release.setDate(release.getDate() + (weekOffset * 7));
    return release;
  },

  _isRolloutEpisode(recordDate) {
    const normalRelease = new Date(recordDate);
    normalRelease.setDate(normalRelease.getDate() + 7);
    return normalRelease <= this.LAUNCH_DATE;
  },

  /**
   * Format episode number as EP001, EP002, etc.
   */
  _formatEpNumber(num) {
    return 'EP' + String(num).padStart(3, '0');
  },

  /**
   * Get the show slot for a specific record date (YYYY-MM-DD string)
   */
  getSlotByRecordDate(dateStr) {
    const slots = Storage.getShowSlots();
    return slots.find(s => s.recordDate === dateStr) || null;
  },

  /**
   * Get all show slots that release on a specific date
   */
  getSlotsByReleaseDate(dateStr) {
    const slots = Storage.getShowSlots();
    return slots.filter(s => s.releaseDate === dateStr);
  },

  /**
   * Get show slot by its ID
   */
  getSlotById(slotId) {
    const slots = Storage.getShowSlots();
    return slots.find(s => s.id === slotId) || null;
  },

  /**
   * Format date for display
   */
  formatDate(dateStr) {
    const d = new Date(dateStr + 'T12:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  },

  formatDateShort(dateStr) {
    const d = new Date(dateStr + 'T12:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  },

  /**
   * Get the effective release date for a slot (override wins)
   */
  getEffectiveReleaseDate(slot) {
    return slot.releaseDateOverride || slot.releaseDate;
  },

  /**
   * Set a custom release date on a slot
   */
  setReleaseDate(slotId, newDate) {
    const slots = Storage.getShowSlots();
    const slot = slots.find(s => s.id === slotId);
    if (!slot) return null;
    slot.releaseDateOverride = newDate;
    Storage.saveShowSlots(slots);
    return slot;
  },

  /**
   * Reset release date back to calculated default
   */
  resetReleaseDate(slotId) {
    const slots = Storage.getShowSlots();
    const slot = slots.find(s => s.id === slotId);
    if (!slot) return null;
    delete slot.releaseDateOverride;
    Storage.saveShowSlots(slots);
    return slot;
  }
};
