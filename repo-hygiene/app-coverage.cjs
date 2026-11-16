'use strict';

const crypto = require('node:crypto');

function requireOrganizationCoverage(installation) {
  if (installation.account?.login !== 'honua-io' ||
      installation.account?.type !== 'Organization' ||
      installation.repository_selection !== 'all' || installation.suspended_at) {
    throw new Error('Weekly reporting requires an active all-repository honua-io App installation');
  }
}

async function checkCoverage() {
  const now = Math.floor(Date.now() / 1000);
  const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url');
  const header = encode({alg: 'RS256', typ: 'JWT'});
  const payload = encode({iat: now - 60, exp: now + 300, iss: process.env.BOT_APP_ID});
  const unsigned = `${header}.${payload}`;
  const signature = crypto.sign('RSA-SHA256', Buffer.from(unsigned),
    process.env.BOT_APP_PRIVATE_KEY).toString('base64url');
  const response = await fetch(`https://api.github.com/app/installations/${process.env.INSTALLATION_ID}`, {
    headers: {Authorization: `Bearer ${unsigned}.${signature}`, Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28'},
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new Error('Could not verify reporting installation coverage');
  requireOrganizationCoverage(await response.json());
  console.log('Verified active all-repository honua-io App installation for weekly reporting');
}

module.exports = {requireOrganizationCoverage, checkCoverage};
if (require.main === module) {
  checkCoverage().catch(() => {
    console.error('Weekly reporting installation coverage could not be verified');
    process.exitCode = 1;
  });
}
