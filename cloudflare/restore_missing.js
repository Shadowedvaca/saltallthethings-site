/**
 * SATT Data Recovery — Restore Missing Episodes
 *
 * Usage:
 *   node restore_missing.js <current_backup.json> <reference_backup.json>
 *
 * This script merges ideas and assignments from the reference backup (Feb 16)
 * back into the current backup WITHOUT overwriting anything that already exists.
 * Only truly missing ideas are added back.
 *
 * Output: restored_YYYYMMDD.json  (ready to push with backup_push.bat)
 */

const fs = require('fs');

const [,, currentFile, referenceFile] = process.argv;
if (!currentFile || !referenceFile) {
  console.error('Usage: node restore_missing.js <current.json> <reference.json>');
  process.exit(1);
}

const current   = JSON.parse(fs.readFileSync(currentFile,   'utf8'));
const reference = JSON.parse(fs.readFileSync(referenceFile, 'utf8'));

// Build sets of existing idea IDs in current data
const currentIdeaIds = new Set((current.ideas || []).map(i => i.id));

// Find ideas that exist in reference but are MISSING from current
const missingIdeas = (reference.ideas || []).filter(i => !currentIdeaIds.has(i.id));

if (missingIdeas.length === 0) {
  console.log('No missing ideas found. Current data already has everything from the reference backup.');
  process.exit(0);
}

console.log(`Found ${missingIdeas.length} missing idea(s) to restore:`);
missingIdeas.forEach(i => {
  const title = i.selectedTitle || (i.titles && i.titles[0]) || 'Untitled';
  console.log(`  + ${i.id} | ${title}`);
});

// Add missing ideas back into current data
const merged = {
  ...current,
  ideas: [...(current.ideas || []), ...missingIdeas],
};

// Restore assignments for the missing ideas (only if the slot isn't already assigned)
const currentAssignments = { ...(current.assignments || {}) };
const referenceAssignments = reference.assignments || {};
const missingIdeaIds = new Set(missingIdeas.map(i => i.id));

let restoredAssignments = 0;
for (const [slotId, ideaId] of Object.entries(referenceAssignments)) {
  if (missingIdeaIds.has(ideaId) && !currentAssignments[slotId]) {
    currentAssignments[slotId] = ideaId;
    restoredAssignments++;
    console.log(`  + Restored assignment: ${slotId} -> ${ideaId}`);
  }
}

merged.assignments = currentAssignments;

// Write output
const date = new Date().toISOString().slice(0,10).replace(/-/g,'');
const outFile = `SITE_DATA_BACKUP_${date}_RESTORED.json`;
fs.writeFileSync(outFile, JSON.stringify(merged, null, 2));

console.log(`\nRestored ${missingIdeas.length} idea(s) and ${restoredAssignments} assignment(s).`);
console.log(`Output written to: ${outFile}`);
console.log(`\nNext step: run backup_push.bat ${outFile}`);
