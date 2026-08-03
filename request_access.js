const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ 
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--lang=en-US,en'],
    headless: true 
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  
  // Go to the Google Sheet
  await page.goto('https://docs.google.com/spreadsheets/d/1pzyG3r9CtMIoHqf62qB6E0pG8Rq3MVr4WZutGe1idxo/edit?usp=drivesdk', { waitUntil: 'networkidle2' });
  
  // Wait for the "View only" / "Nur Lesezugriff" button
  // We can look for the element by id="docs-access-level-indicator"
  try {
    await page.waitForSelector('#docs-access-level-indicator', { timeout: 10000 });
    console.log("Found access level indicator, clicking it...");
    await page.click('#docs-access-level-indicator');
    
    await new Promise(r => setTimeout(r, 2000));
    
    // Take screenshot to see the menu
    await page.screenshot({ path: '/home/students/.gemini/antigravity-cli/brain/623e35f6-13d3-4fd9-b81e-e2dd718c67f2/request_access_menu.png' });
    
    console.log("Screenshot taken.");
  } catch (e) {
    console.log("Error: " + e.message);
    await page.screenshot({ path: '/home/students/.gemini/antigravity-cli/brain/623e35f6-13d3-4fd9-b81e-e2dd718c67f2/request_access_error.png' });
  }

  await browser.close();
})();
