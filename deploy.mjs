// Deploy BlessedScroll to VM02: ships the committed tree (git archive HEAD) into
// ~/blessedscroll, leaving the Twitter archive, data/ cache and super_likes.txt
// alone, then restarts the p90zone container.   Usage: node deploy.mjs
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const { Client } = createRequire(import.meta.url)('/home/dillon/orb/node_modules/ssh2');

const HOST = process.env.HOST || '192.168.1.197';
const pw = readFileSync('/home/dillon/orb/.env.local', 'utf8')
  .match(/^ORB_SSH_PASSWORD=(.*)$/m)[1].replace(/^["']|["']$/g, '');
if (execSync('git status --porcelain').toString().trim())
  console.warn('!! uncommitted changes are NOT deployed (git archive HEAD)');
const tar = execSync('git archive --format=tar.gz HEAD');
const rev = execSync('git rev-parse --short HEAD').toString().trim();

const remote = `set -e; cd ~/blessedscroll
mkdir -p .deploy-bak && tar czf .deploy-bak/pre-${rev}-$(date +%Y%m%d-%H%M%S).tgz --exclude=./twitter-* --exclude=./data --exclude=./.git --exclude=./.deploy-bak --exclude='./p90zone*' --exclude=./tweets.json .
base64 -d | tar xzf -
git fetch -q origin 2>/dev/null && git reset -q origin/master 2>/dev/null || true
docker restart p90zone >/dev/null
for i in $(seq 1 20); do curl -sf localhost:9090/status && exit 0; sleep 1; done
echo "server did not come up"; docker logs --tail 30 p90zone; exit 1`;

const c = new Client();
c.on('ready', () => c.exec(remote, (err, s) => {
  if (err) throw err;
  s.on('close', code => { c.end(); console.log(code ? `\ndeploy FAILED (${code})` : `\ndeployed ${rev} to ${HOST}:9090`); process.exit(code || 0); });
  s.pipe(process.stdout); s.stderr.pipe(process.stderr);
  s.end(tar.toString('base64'));
})).connect({ host: HOST, username: 'dillon', password: pw });
