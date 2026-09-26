/*
 * better-sqlite3 contient un petit module natif lié à la version de Node.js.
 * Ce contrôle reconstruit automatiquement ce module lorsqu'un dossier
 * node_modules a été créé avec une autre version de Node.
 */
const { spawnSync } = require("node:child_process");

function sqliteWorks() {
  try {
    const Database = require("better-sqlite3");
    const database = new Database(":memory:");
    database.prepare("SELECT 1").get();
    database.close();
    return true;
  } catch (error) {
    if (process.env.STATION_SQLITE_VERBOSE === "1") {
      console.error(error);
    }
    return false;
  }
}

if (!sqliteWorks()) {
  console.log(`SQLite doit être adapté à Node.js ${process.version}. Reconstruction automatique…`);
  const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
  const rebuild = spawnSync(npmCommand, ["rebuild", "better-sqlite3"], {
    stdio: "inherit",
    shell: false,
  });

  if (rebuild.status !== 0 || !sqliteWorks()) {
    console.error("La reconstruction de SQLite a échoué. Vérifiez que npm et les outils de compilation sont installés.");
    process.exit(1);
  }

  console.log("SQLite est maintenant compatible avec cette version de Node.js.");
}
