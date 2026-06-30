import url from 'url';
import { createRunner } from '@puppeteer/replay';

export async function run(extension) {
    const runner = await createRunner(extension);

    await runner.runBeforeAllSteps();

    await runner.runStep({
        type: 'setViewport',
        width: 1004,
        height: 914,
        deviceScaleFactor: 1,
        isMobile: false,
        hasTouch: false,
        isLandscape: false
    });
    await runner.runStep({
        type: 'navigate',
        url: 'http://localhost:5173/',
        assertedEvents: [
            {
                type: 'navigation',
                url: 'http://localhost:5173/',
                title: 'ReqFlow'
            }
        ]
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='workspace-card'] > div:nth-of-type(1) > div:nth-of-type(2)"
            ],
            [
                'xpath///*[@data-testid="workspace-card"]/div[1]/div[2]'
            ],
            [
                "pierce/[data-testid='workspace-card'] > div:nth-of-type(1) > div:nth-of-type(2)"
            ],
            [
                'text/SE-Modus'
            ]
        ],
        offsetY: 9,
        offsetX: 65,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'li:nth-of-type(2) > span:nth-of-type(1)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[1]/ul/li[2]/span[1]'
            ],
            [
                'pierce/li:nth-of-type(2) > span:nth-of-type(1)'
            ],
            [
                'text/Das ist eine'
            ]
        ],
        offsetY: 2,
        offsetX: 146,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/View Diff'
            ],
            [
                "[data-testid='view-diff-btn']"
            ],
            [
                'xpath///*[@data-testid="view-diff-btn"]'
            ],
            [
                "pierce/[data-testid='view-diff-btn']"
            ],
            [
                'text/View Diff'
            ]
        ],
        offsetY: 21,
        offsetX: 36.953125,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/From:'
            ],
            [
                "[data-testid='diff-from-version']"
            ],
            [
                'xpath///*[@data-testid="diff-from-version"]'
            ],
            [
                "pierce/[data-testid='diff-from-version']"
            ]
        ],
        offsetY: 7,
        offsetX: 109,
    });
    await runner.runStep({
        type: 'change',
        value: '1',
        selectors: [
            [
                'aria/From:'
            ],
            [
                "[data-testid='diff-from-version']"
            ],
            [
                'xpath///*[@data-testid="diff-from-version"]'
            ],
            [
                "pierce/[data-testid='diff-from-version']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/To:'
            ],
            [
                "[data-testid='diff-to-version']"
            ],
            [
                'xpath///*[@data-testid="diff-to-version"]'
            ],
            [
                "pierce/[data-testid='diff-to-version']"
            ]
        ],
        offsetY: 13,
        offsetX: 48,
    });
    await runner.runStep({
        type: 'change',
        value: '0',
        selectors: [
            [
                'aria/To:'
            ],
            [
                "[data-testid='diff-to-version']"
            ],
            [
                'xpath///*[@data-testid="diff-to-version"]'
            ],
            [
                "pierce/[data-testid='diff-to-version']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='artifact-diff-view']"
            ],
            [
                'xpath///*[@data-testid="artifact-diff-view"]'
            ],
            [
                "pierce/[data-testid='artifact-diff-view']"
            ]
        ],
        offsetY: 152,
        offsetX: 10,
        duration: 658,
    });
    await runner.runStep({
        type: 'doubleClick',
        target: 'main',
        selectors: [
            [
                "[data-testid='diff-error']"
            ],
            [
                'xpath///*[@data-testid="diff-error"]'
            ],
            [
                "pierce/[data-testid='diff-error']"
            ],
            [
                'text/Error: [object'
            ]
        ],
        offsetY: 19,
        offsetX: 183,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/To:'
            ],
            [
                "[data-testid='diff-to-version']"
            ],
            [
                'xpath///*[@data-testid="diff-to-version"]'
            ],
            [
                "pierce/[data-testid='diff-to-version']"
            ]
        ],
        offsetY: 12,
        offsetX: 80,
    });
    await runner.runStep({
        type: 'change',
        value: '1',
        selectors: [
            [
                'aria/To:'
            ],
            [
                "[data-testid='diff-to-version']"
            ],
            [
                'xpath///*[@data-testid="diff-to-version"]'
            ],
            [
                "pierce/[data-testid='diff-to-version']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='diff-version-selectors']"
            ],
            [
                'xpath///*[@data-testid="diff-version-selectors"]'
            ],
            [
                "pierce/[data-testid='diff-version-selectors']"
            ],
            [
                'text/From:1→To:1'
            ]
        ],
        offsetY: 52,
        offsetX: 136,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/From:'
            ],
            [
                "[data-testid='diff-from-version']"
            ],
            [
                'xpath///*[@data-testid="diff-from-version"]'
            ],
            [
                "pierce/[data-testid='diff-from-version']"
            ]
        ],
        offsetY: 16,
        offsetX: 81,
    });
    await runner.runStep({
        type: 'change',
        value: '0',
        selectors: [
            [
                'aria/From:'
            ],
            [
                "[data-testid='diff-from-version']"
            ],
            [
                'xpath///*[@data-testid="diff-from-version"]'
            ],
            [
                "pierce/[data-testid='diff-from-version']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Neuen Link erstellen'
            ],
            [
                "[data-testid='req-tracelink-create-btn']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-create-btn"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-create-btn']"
            ],
            [
                'text/Neuen Link erstellen'
            ]
        ],
        offsetY: 9,
        offsetX: 65.9375,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='req-tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-target-select']"
            ]
        ],
        offsetY: 6,
        offsetX: 80,
    });
    await runner.runStep({
        type: 'change',
        value: '2ababa20-c639-4ba0-b48b-bc3ac5541bf2',
        selectors: [
            [
                "[data-testid='req-tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-target-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Erstellen'
            ],
            [
                "[data-testid='req-tracelink-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-submit-btn"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-submit-btn']"
            ],
            [
                'text/Erstellen'
            ]
        ],
        offsetY: 15,
        offsetX: 61.140625,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='req-tracelink-type-select']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-type-select"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-type-select']"
            ]
        ],
        offsetY: 18,
        offsetX: 117,
    });
    await runner.runStep({
        type: 'change',
        value: 'verifies',
        selectors: [
            [
                "[data-testid='req-tracelink-type-select']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-type-select"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-type-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Erstellen'
            ],
            [
                "[data-testid='req-tracelink-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-submit-btn"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-submit-btn']"
            ],
            [
                'text/Erstellen'
            ]
        ],
        offsetY: 18,
        offsetX: 47.140625,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='req-tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-target-select']"
            ],
            [
                'text/2ababa20-c639-4ba0-b48b-bc3ac5541bf2'
            ]
        ],
        offsetY: 15,
        offsetX: 117,
    });
    await runner.runStep({
        type: 'change',
        value: '4ca92b74-f85e-4404-bc01-e8694d4bff82',
        selectors: [
            [
                "[data-testid='req-tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-target-select']"
            ],
            [
                'text/2ababa20-c639-4ba0-b48b-bc3ac5541bf2'
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='diff-field-title']"
            ],
            [
                'xpath///*[@data-testid="diff-field-title"]'
            ],
            [
                "pierce/[data-testid='diff-field-title']"
            ],
            [
                'text/titleAddedDas'
            ]
        ],
        offsetY: 47,
        offsetX: 124,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Erstellen'
            ],
            [
                "[data-testid='req-tracelink-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="req-tracelink-submit-btn"]'
            ],
            [
                "pierce/[data-testid='req-tracelink-submit-btn']"
            ],
            [
                'text/Erstellen'
            ]
        ],
        offsetY: 20,
        offsetX: 59.140625,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Architektur'
            ],
            [
                'li:nth-of-type(3) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[3]/a'
            ],
            [
                'pierce/li:nth-of-type(3) > a'
            ],
            [
                'text/Architektur'
            ]
        ],
        offsetY: 11,
        offsetX: 54,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'li:nth-of-type(1) > span:nth-of-type(1)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[1]/ul/li[1]/span[1]'
            ],
            [
                'pierce/li:nth-of-type(1) > span:nth-of-type(1)'
            ],
            [
                'text/Neues Element'
            ]
        ],
        offsetY: 5.5,
        offsetX: 305,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Element-Typ'
            ],
            [
                "[data-testid='arch-element-type-select']"
            ],
            [
                'xpath///*[@data-testid="arch-element-type-select"]'
            ],
            [
                "pierce/[data-testid='arch-element-type-select']"
            ],
            [
                'text/component'
            ]
        ],
        offsetY: 18,
        offsetX: 102,
    });
    await runner.runStep({
        type: 'change',
        value: 'subsystem',
        selectors: [
            [
                'aria/Element-Typ'
            ],
            [
                "[data-testid='arch-element-type-select']"
            ],
            [
                'xpath///*[@data-testid="arch-element-type-select"]'
            ],
            [
                "pierce/[data-testid='arch-element-type-select']"
            ],
            [
                'text/component'
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Neuen Link erstellen'
            ],
            [
                "[data-testid='arch-tracelink-create-btn']"
            ],
            [
                'xpath///*[@data-testid="arch-tracelink-create-btn"]'
            ],
            [
                "pierce/[data-testid='arch-tracelink-create-btn']"
            ],
            [
                'text/Neuen Link erstellen'
            ]
        ],
        offsetY: 2,
        offsetX: 71,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='arch-tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="arch-tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='arch-tracelink-target-select']"
            ]
        ],
        offsetY: 20,
        offsetX: 79,
    });
    await runner.runStep({
        type: 'change',
        value: '3eef87ab-5432-40ad-ada3-01d00bbb9669',
        selectors: [
            [
                "[data-testid='arch-tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="arch-tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='arch-tracelink-target-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Erstellen'
            ],
            [
                "[data-testid='arch-tracelink-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="arch-tracelink-submit-btn"]'
            ],
            [
                "pierce/[data-testid='arch-tracelink-submit-btn']"
            ],
            [
                'text/Erstellen'
            ]
        ],
        offsetY: 12,
        offsetX: 35.125,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Speichern'
            ],
            [
                "[data-testid='arch-save-btn']"
            ],
            [
                'xpath///*[@data-testid="arch-save-btn"]'
            ],
            [
                "pierce/[data-testid='arch-save-btn']"
            ],
            [
                'text/Speichern'
            ]
        ],
        offsetY: 20,
        offsetX: 51,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'div:nth-of-type(2) > div > div'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/div/div'
            ],
            [
                'pierce/div:nth-of-type(2) > div > div'
            ]
        ],
        offsetY: 545,
        offsetX: 142,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'div:nth-of-type(1) > p'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/div/div/div[1]/p'
            ],
            [
                'pierce/div:nth-of-type(1) > p'
            ]
        ],
        offsetY: 33,
        offsetX: 208,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/View Diff'
            ],
            [
                "[data-testid='arch-view-diff-btn']"
            ],
            [
                'xpath///*[@data-testid="arch-view-diff-btn"]'
            ],
            [
                "pierce/[data-testid='arch-view-diff-btn']"
            ],
            [
                'text/View Diff'
            ]
        ],
        offsetY: 15,
        offsetX: 48.234375,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='diff-version-selectors']"
            ],
            [
                'xpath///*[@data-testid="diff-version-selectors"]'
            ],
            [
                "pierce/[data-testid='diff-version-selectors']"
            ],
            [
                'text/From:→To:'
            ]
        ],
        offsetY: 26,
        offsetX: 94,
    });
    await runner.runStep({
        type: 'doubleClick',
        target: 'main',
        selectors: [
            [
                'aria/From:'
            ],
            [
                "[data-testid='diff-from-version']"
            ],
            [
                'xpath///*[@data-testid="diff-from-version"]'
            ],
            [
                "pierce/[data-testid='diff-from-version']"
            ]
        ],
        offsetY: 18,
        offsetX: 27.546875,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='artifact-diff-view']"
            ],
            [
                'xpath///*[@data-testid="artifact-diff-view"]'
            ],
            [
                "pierce/[data-testid='artifact-diff-view']"
            ],
            [
                'text/Architecture Element DiffCloseFrom:→To:Error:'
            ]
        ],
        offsetY: 52,
        offsetX: 238,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Close'
            ],
            [
                "[data-testid='diff-close-btn']"
            ],
            [
                'xpath///*[@data-testid="diff-close-btn"]'
            ],
            [
                "pierce/[data-testid='diff-close-btn']"
            ],
            [
                'text/Close'
            ]
        ],
        offsetY: 12,
        offsetX: 18.546875,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/ADRs'
            ],
            [
                'li:nth-of-type(4) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[4]/a'
            ],
            [
                'pierce/li:nth-of-type(4) > a'
            ],
            [
                'text/ADRs'
            ]
        ],
        offsetY: 23,
        offsetX: 41,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/[role="main"]',
                'aria/[role="paragraph"]'
            ],
            [
                'p'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/p'
            ],
            [
                'pierce/p'
            ],
            [
                'text/Keine Einträge'
            ]
        ],
        offsetY: 30,
        offsetX: 228,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'main'
            ],
            [
                'xpath///*[@id="root"]/div/main'
            ],
            [
                'pierce/main'
            ]
        ],
        offsetY: 168,
        offsetX: 521,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'main'
            ],
            [
                'xpath///*[@id="root"]/div/main'
            ],
            [
                'pierce/main'
            ]
        ],
        offsetY: 307,
        offsetX: 204,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Risiken'
            ],
            [
                'li:nth-of-type(5) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[5]/a'
            ],
            [
                'pierce/li:nth-of-type(5) > a'
            ],
            [
                'text/Risiken'
            ]
        ],
        offsetY: 10,
        offsetX: 67,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Probleme'
            ],
            [
                'li:nth-of-type(6) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[6]/a'
            ],
            [
                'pierce/li:nth-of-type(6) > a'
            ],
            [
                'text/Probleme'
            ]
        ],
        offsetY: 21,
        offsetX: 53,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Testläufe'
            ],
            [
                'li:nth-of-type(7) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[7]/a'
            ],
            [
                'pierce/li:nth-of-type(7) > a'
            ],
            [
                'text/Testläufe'
            ]
        ],
        offsetY: 21,
        offsetX: 66,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/+ Testlauf erstellen'
            ],
            [
                'main button'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div/button'
            ],
            [
                'pierce/main button'
            ],
            [
                'text/+ Testlauf erstellen'
            ]
        ],
        offsetY: 11,
        offsetX: 73.203125,
    });
    await runner.runStep({
        type: 'change',
        value: 'a',
        selectors: [
            [
                'aria/Name des Testlaufs...'
            ],
            [
                'main input'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/input'
            ],
            [
                'pierce/main input'
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Name des Testlaufs...'
            ],
            [
                'main input'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/input'
            ],
            [
                'pierce/main input'
            ]
        ],
        offsetY: 9,
        offsetX: 153,
    });
    await runner.runStep({
        type: 'change',
        value: 'asdasdasd',
        selectors: [
            [
                'aria/Name des Testlaufs...'
            ],
            [
                'main input'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/input'
            ],
            [
                'pierce/main input'
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Create'
            ],
            [
                'div:nth-of-type(2) > button:nth-of-type(1)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/button[1]'
            ],
            [
                'pierce/div:nth-of-type(2) > button:nth-of-type(1)'
            ],
            [
                'text/Create'
            ]
        ],
        offsetY: 13,
        offsetX: 48.3125,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'li:nth-of-type(1) > span'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/ul/li[1]/span'
            ],
            [
                'pierce/li:nth-of-type(1) > span'
            ]
        ],
        offsetY: 6,
        offsetX: 78.296875,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(1)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/div[2]/div[1]'
            ],
            [
                'pierce/div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(1)'
            ]
        ],
        offsetY: 13,
        offsetX: 85,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(1)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/div[2]/div[1]'
            ],
            [
                'pierce/div:nth-of-type(2) > div:nth-of-type(2) > div:nth-of-type(1)'
            ]
        ],
        offsetY: 16,
        offsetX: 115,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Testlauf abschließen'
            ],
            [
                'main button:nth-of-type(2)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/button[2]'
            ],
            [
                'pierce/main button:nth-of-type(2)'
            ],
            [
                'text/Testlauf abschließen'
            ]
        ],
        offsetY: 22,
        offsetX: 65,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Testlauf abschließen'
            ],
            [
                'main button:nth-of-type(2)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/button[2]'
            ],
            [
                'pierce/main button:nth-of-type(2)'
            ],
            [
                'text/Testlauf abschließen'
            ]
        ],
        offsetY: 12,
        offsetX: 81,
    });
    await runner.runStep({
        type: 'doubleClick',
        target: 'main',
        selectors: [
            [
                'aria/Testlauf abschließen'
            ],
            [
                'main button:nth-of-type(2)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/button[2]'
            ],
            [
                'pierce/main button:nth-of-type(2)'
            ],
            [
                'text/Testlauf abschließen'
            ]
        ],
        offsetY: 17,
        offsetX: 158,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'div:nth-of-type(2) > div:nth-of-type(1) > div:nth-of-type(2)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/div[1]/div[2]'
            ],
            [
                'pierce/div:nth-of-type(2) > div:nth-of-type(1) > div:nth-of-type(2)'
            ],
            [
                'text/Total'
            ]
        ],
        offsetY: 2,
        offsetX: 93,
    });
    await runner.runStep({
        type: 'doubleClick',
        target: 'main',
        selectors: [
            [
                'aria/Testlauf abschließen'
            ],
            [
                'main button:nth-of-type(2)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/button[2]'
            ],
            [
                'pierce/main button:nth-of-type(2)'
            ],
            [
                'text/Testlauf abschließen'
            ]
        ],
        offsetY: 17,
        offsetX: 45,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Testlauf abschließen'
            ],
            [
                'main button:nth-of-type(2)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/button[2]'
            ],
            [
                'pierce/main button:nth-of-type(2)'
            ],
            [
                'text/Testlauf abschließen'
            ]
        ],
        offsetY: 23,
        offsetX: 44,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Testlauf abschließen'
            ],
            [
                'main button:nth-of-type(2)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/button[2]'
            ],
            [
                'pierce/main button:nth-of-type(2)'
            ],
            [
                'text/Testlauf abschließen'
            ]
        ],
        offsetY: 29,
        offsetX: 46,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Testlauf abschließen'
            ],
            [
                'main button:nth-of-type(2)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/button[2]'
            ],
            [
                'pierce/main button:nth-of-type(2)'
            ],
            [
                'text/Testlauf abschließen'
            ]
        ],
        offsetY: 21,
        offsetX: 55,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'main > div > div:nth-of-type(2) > div:nth-of-type(1)'
            ],
            [
                'xpath///*[@id="root"]/div/main/div/div[2]/div[1]'
            ],
            [
                'pierce/main > div > div:nth-of-type(2) > div:nth-of-type(1)'
            ],
            [
                'text/0Total'
            ]
        ],
        offsetY: 60,
        offsetX: 29,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'main'
            ],
            [
                'xpath///*[@id="root"]/div/main'
            ],
            [
                'pierce/main'
            ]
        ],
        offsetY: 297,
        offsetX: 145,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Traceability'
            ],
            [
                'li:nth-of-type(8) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[8]/a'
            ],
            [
                'pierce/li:nth-of-type(8) > a'
            ],
            [
                'text/Traceability'
            ]
        ],
        offsetY: 8,
        offsetX: 73,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Neuen Link erstellen'
            ],
            [
                "[data-testid='tracelink-create-btn']"
            ],
            [
                'xpath///*[@data-testid="tracelink-create-btn"]'
            ],
            [
                "pierce/[data-testid='tracelink-create-btn']"
            ],
            [
                'text/Neuen Link erstellen'
            ]
        ],
        offsetY: 25,
        offsetX: 55.875,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Ziel'
            ],
            [
                "[data-testid='tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-target-select']"
            ]
        ],
        offsetY: 3,
        offsetX: 167,
    });
    await runner.runStep({
        type: 'change',
        value: 'b2d5b075-1688-47aa-85eb-213bc5b68c91',
        selectors: [
            [
                'aria/Ziel'
            ],
            [
                "[data-testid='tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-target-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Quelle'
            ],
            [
                "[data-testid='tracelink-source-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-source-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-source-select']"
            ]
        ],
        offsetY: 24,
        offsetX: 88,
    });
    await runner.runStep({
        type: 'change',
        value: '569d84e8-4e7b-4965-a2de-ac9f23e42e7f',
        selectors: [
            [
                'aria/Quelle'
            ],
            [
                "[data-testid='tracelink-source-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-source-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-source-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Link-Typ'
            ],
            [
                "[data-testid='tracelink-type-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-type-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-type-select']"
            ]
        ],
        offsetY: 15,
        offsetX: 101,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Erstellen'
            ],
            [
                "[data-testid='tracelink-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="tracelink-submit-btn"]'
            ],
            [
                "pierce/[data-testid='tracelink-submit-btn']"
            ],
            [
                'text/Erstellen'
            ]
        ],
        offsetY: 19,
        offsetX: 39.25,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Neuen Link erstellen'
            ],
            [
                "[data-testid='tracelink-create-btn']"
            ],
            [
                'xpath///*[@data-testid="tracelink-create-btn"]'
            ],
            [
                "pierce/[data-testid='tracelink-create-btn']"
            ],
            [
                'text/Neuen Link erstellen'
            ]
        ],
        offsetY: 6,
        offsetX: 66.875,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Ziel'
            ],
            [
                "[data-testid='tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-target-select']"
            ]
        ],
        offsetY: 32,
        offsetX: 114,
    });
    await runner.runStep({
        type: 'change',
        value: 'dcef7414-cad4-4f39-b7d3-5483ca73e05e',
        selectors: [
            [
                'aria/Ziel'
            ],
            [
                "[data-testid='tracelink-target-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-target-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-target-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'doubleClick',
        target: 'main',
        selectors: [
            [
                'aria/Quelle'
            ],
            [
                "[data-testid='tracelink-source-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-source-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-source-select']"
            ]
        ],
        offsetY: 22,
        offsetX: 106,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Quelle'
            ],
            [
                "[data-testid='tracelink-source-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-source-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-source-select']"
            ]
        ],
        offsetY: 32,
        offsetX: 141,
    });
    await runner.runStep({
        type: 'change',
        value: '732098a7-ea24-4e8e-a224-ae517f04821e',
        selectors: [
            [
                'aria/Quelle'
            ],
            [
                "[data-testid='tracelink-source-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-source-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-source-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Link-Typ'
            ],
            [
                "[data-testid='tracelink-type-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-type-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-type-select']"
            ]
        ],
        offsetY: 11,
        offsetX: 77,
    });
    await runner.runStep({
        type: 'change',
        value: 'implements',
        selectors: [
            [
                'aria/Link-Typ'
            ],
            [
                "[data-testid='tracelink-type-select']"
            ],
            [
                'xpath///*[@data-testid="tracelink-type-select"]'
            ],
            [
                "pierce/[data-testid='tracelink-type-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Erstellen'
            ],
            [
                "[data-testid='tracelink-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="tracelink-submit-btn"]'
            ],
            [
                "pierce/[data-testid='tracelink-submit-btn']"
            ],
            [
                'text/Erstellen'
            ]
        ],
        offsetY: 15,
        offsetX: 40.25,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Baselines'
            ],
            [
                'li:nth-of-type(9) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[9]/a'
            ],
            [
                'pierce/li:nth-of-type(9) > a'
            ],
            [
                'text/Baselines'
            ]
        ],
        offsetY: 18,
        offsetX: 55,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/+ Neue Baseline'
            ],
            [
                "[data-testid='create-baseline-btn']"
            ],
            [
                'xpath///*[@data-testid="create-baseline-btn"]'
            ],
            [
                "pierce/[data-testid='create-baseline-btn']"
            ],
            [
                'text/+ Neue Baseline'
            ]
        ],
        offsetY: 18,
        offsetX: 35.140625,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'label:nth-of-type(1) > span'
            ],
            [
                'xpath///*[@data-testid="baseline-scope-group"]/label[1]/span'
            ],
            [
                'pierce/label:nth-of-type(1) > span'
            ],
            [
                'text/Dokument (einzelnes'
            ]
        ],
        offsetY: 2,
        offsetX: 27,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Speichern'
            ],
            [
                "[data-testid='baseline-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="baseline-submit-btn"]'
            ],
            [
                "pierce/[data-testid='baseline-submit-btn']"
            ],
            [
                'text/Speichern'
            ]
        ],
        offsetY: 18,
        offsetX: 47,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Artefakt'
            ],
            [
                "[data-testid='baseline-artifact-select']"
            ],
            [
                'xpath///*[@data-testid="baseline-artifact-select"]'
            ],
            [
                "pierce/[data-testid='baseline-artifact-select']"
            ],
            [
                'text/871b7246-d016-4926-a8fa-ffd36df47f01'
            ]
        ],
        offsetY: 9,
        offsetX: 134,
    });
    await runner.runStep({
        type: 'change',
        value: 'b2d5b075-1688-47aa-85eb-213bc5b68c91',
        selectors: [
            [
                'aria/Artefakt'
            ],
            [
                "[data-testid='baseline-artifact-select']"
            ],
            [
                'xpath///*[@data-testid="baseline-artifact-select"]'
            ],
            [
                "pierce/[data-testid='baseline-artifact-select']"
            ],
            [
                'text/871b7246-d016-4926-a8fa-ffd36df47f01'
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Speichern'
            ],
            [
                "[data-testid='baseline-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="baseline-submit-btn"]'
            ],
            [
                "pierce/[data-testid='baseline-submit-btn']"
            ],
            [
                'text/Speichern'
            ]
        ],
        offsetY: 20,
        offsetX: 63,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='baseline-scope-group'] > label:nth-of-type(2)"
            ],
            [
                'xpath///*[@data-testid="baseline-scope-group"]/label[2]'
            ],
            [
                "pierce/[data-testid='baseline-scope-group'] > label:nth-of-type(2)"
            ]
        ],
        offsetY: 11,
        offsetX: 21,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Projekt (alle Artefakte im Workspace)'
            ],
            [
                "[data-testid='baseline-scope-project']"
            ],
            [
                'xpath///*[@data-testid="baseline-scope-project"]'
            ],
            [
                "pierce/[data-testid='baseline-scope-project']"
            ]
        ],
        offsetY: 8,
        offsetX: 16,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Speichern'
            ],
            [
                "[data-testid='baseline-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="baseline-submit-btn"]'
            ],
            [
                "pierce/[data-testid='baseline-submit-btn']"
            ],
            [
                'text/Speichern'
            ]
        ],
        offsetY: 20,
        offsetX: 52,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Global (alle Artefakte im Tenant — nur Admins)'
            ],
            [
                "[data-testid='baseline-scope-global']"
            ],
            [
                'xpath///*[@data-testid="baseline-scope-global"]'
            ],
            [
                "pierce/[data-testid='baseline-scope-global']"
            ]
        ],
        offsetY: 12,
        offsetX: 12,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Speichern'
            ],
            [
                "[data-testid='baseline-submit-btn']"
            ],
            [
                'xpath///*[@data-testid="baseline-submit-btn"]'
            ],
            [
                "pierce/[data-testid='baseline-submit-btn']"
            ],
            [
                'text/Speichern'
            ]
        ],
        offsetY: 30,
        offsetX: 45,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Import'
            ],
            [
                'li:nth-of-type(10) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[10]/a'
            ],
            [
                'pierce/li:nth-of-type(10) > a'
            ],
            [
                'text/Import'
            ]
        ],
        offsetY: 16,
        offsetX: 105,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'label:nth-of-type(2)'
            ],
            [
                'xpath///*[@data-testid="csv-import-page"]/section[1]/div/label[2]'
            ],
            [
                'pierce/label:nth-of-type(2)'
            ],
            [
                'text/ArchitectureElement'
            ]
        ],
        offsetY: 16.09375,
        offsetX: 60.84375,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/ArchitectureElement'
            ],
            [
                "[data-testid='entity-type-ArchitectureElement']"
            ],
            [
                'xpath///*[@data-testid="entity-type-ArchitectureElement"]'
            ],
            [
                "pierce/[data-testid='entity-type-ArchitectureElement']"
            ]
        ],
        offsetY: 4.09375,
        offsetX: 42.84375,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'label:nth-of-type(3)'
            ],
            [
                'xpath///*[@data-testid="csv-import-page"]/section[1]/div/label[3]'
            ],
            [
                'pierce/label:nth-of-type(3)'
            ],
            [
                'text/TestCase'
            ]
        ],
        offsetY: 12.09375,
        offsetX: 68.78125,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/TestCase'
            ],
            [
                "[data-testid='entity-type-TestCase']"
            ],
            [
                'xpath///*[@data-testid="entity-type-TestCase"]'
            ],
            [
                "pierce/[data-testid='entity-type-TestCase']"
            ]
        ],
        offsetY: 0.09375,
        offsetX: 50.78125,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'label:nth-of-type(1)'
            ],
            [
                'xpath///*[@data-testid="csv-import-page"]/section[1]/div/label[1]'
            ],
            [
                'pierce/label:nth-of-type(1)'
            ]
        ],
        offsetY: 14.09375,
        offsetX: 39,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Requirement'
            ],
            [
                "[data-testid='entity-type-Requirement']"
            ],
            [
                'xpath///*[@data-testid="entity-type-Requirement"]'
            ],
            [
                "pierce/[data-testid='entity-type-Requirement']"
            ]
        ],
        offsetY: 2.09375,
        offsetX: 21,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/ICDs'
            ],
            [
                'li:nth-of-type(11) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[11]/a'
            ],
            [
                'pierce/li:nth-of-type(11) > a'
            ],
            [
                'text/ICDs'
            ]
        ],
        offsetY: 4,
        offsetX: 55,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/+ Neues ICD'
            ],
            [
                "[data-testid='create-icd-btn']"
            ],
            [
                'xpath///*[@data-testid="create-icd-btn"]'
            ],
            [
                "pierce/[data-testid='create-icd-btn']"
            ],
            [
                'text/+ Neues ICD'
            ]
        ],
        offsetY: 13,
        offsetX: 49.546875,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/ICD-Name'
            ],
            [
                "[data-testid='icd-name-input']"
            ],
            [
                'xpath///*[@data-testid="icd-name-input"]'
            ],
            [
                "pierce/[data-testid='icd-name-input']"
            ]
        ],
        offsetY: 37,
        offsetX: 67,
    });
    await runner.runStep({
        type: 'change',
        value: 'asdA',
        selectors: [
            [
                'aria/ICD-Name'
            ],
            [
                "[data-testid='icd-name-input']"
            ],
            [
                'xpath///*[@data-testid="icd-name-input"]'
            ],
            [
                "pierce/[data-testid='icd-name-input']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 'D',
        target: 'main'
    });
    await runner.runStep({
        type: 'change',
        value: 'asdASD',
        selectors: [
            [
                'aria/ICD-Name'
            ],
            [
                "[data-testid='icd-name-input']"
            ],
            [
                'xpath///*[@data-testid="icd-name-input"]'
            ],
            [
                "pierce/[data-testid='icd-name-input']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 'a',
        target: 'main'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 's',
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Quell-Element'
            ],
            [
                "[data-testid='icd-source-select']"
            ],
            [
                'xpath///*[@data-testid="icd-source-select"]'
            ],
            [
                "pierce/[data-testid='icd-source-select']"
            ]
        ],
        offsetY: 14,
        offsetX: 98,
    });
    await runner.runStep({
        type: 'change',
        value: '31f512c4-e5ed-477c-8990-d82acf131380',
        selectors: [
            [
                'aria/Quell-Element'
            ],
            [
                "[data-testid='icd-source-select']"
            ],
            [
                'xpath///*[@data-testid="icd-source-select"]'
            ],
            [
                "pierce/[data-testid='icd-source-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Ziel-Element'
            ],
            [
                "[data-testid='icd-target-select']"
            ],
            [
                'xpath///*[@data-testid="icd-target-select"]'
            ],
            [
                "pierce/[data-testid='icd-target-select']"
            ]
        ],
        offsetY: 29,
        offsetX: 86,
    });
    await runner.runStep({
        type: 'change',
        value: '12c2bad1-02b0-4602-b47c-0c2afecb57c3',
        selectors: [
            [
                'aria/Ziel-Element'
            ],
            [
                "[data-testid='icd-target-select']"
            ],
            [
                'xpath///*[@data-testid="icd-target-select"]'
            ],
            [
                "pierce/[data-testid='icd-target-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Richtung'
            ],
            [
                "[data-testid='icd-direction-select']"
            ],
            [
                'xpath///*[@data-testid="icd-direction-select"]'
            ],
            [
                "pierce/[data-testid='icd-direction-select']"
            ],
            [
                'text/unidirectional'
            ]
        ],
        offsetY: 15,
        offsetX: 64,
    });
    await runner.runStep({
        type: 'change',
        value: 'bidirectional',
        selectors: [
            [
                'aria/Richtung'
            ],
            [
                "[data-testid='icd-direction-select']"
            ],
            [
                'xpath///*[@data-testid="icd-direction-select"]'
            ],
            [
                "pierce/[data-testid='icd-direction-select']"
            ],
            [
                'text/unidirectional'
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'keyDown',
        target: 'main',
        key: 'a'
    });
    await runner.runStep({
        type: 'keyDown',
        target: 'main',
        key: 's'
    });
    await runner.runStep({
        type: 'keyDown',
        target: 'main',
        key: 'f'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 'a',
        target: 'main'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 's',
        target: 'main'
    });
    await runner.runStep({
        type: 'keyDown',
        target: 'main',
        key: 'a'
    });
    await runner.runStep({
        type: 'keyDown',
        target: 'main',
        key: 's'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 'f',
        target: 'main'
    });
    await runner.runStep({
        type: 'keyDown',
        target: 'main',
        key: 'd'
    });
    await runner.runStep({
        type: 'keyDown',
        target: 'main',
        key: 'f'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 'a',
        target: 'main'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 's',
        target: 'main'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 'd',
        target: 'main'
    });
    await runner.runStep({
        type: 'keyDown',
        target: 'main',
        key: 'a'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 'f',
        target: 'main'
    });
    await runner.runStep({
        type: 'keyUp',
        key: 'a',
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Schnittstellentyp'
            ],
            [
                "[data-testid='icd-interface-type-input']"
            ],
            [
                'xpath///*[@data-testid="icd-interface-type-input"]'
            ],
            [
                "pierce/[data-testid='icd-interface-type-input']"
            ]
        ],
        offsetY: 14,
        offsetX: 60,
    });
    await runner.runStep({
        type: 'change',
        value: 'asdfasdf',
        selectors: [
            [
                'aria/Schnittstellentyp'
            ],
            [
                "[data-testid='icd-interface-type-input']"
            ],
            [
                'xpath///*[@data-testid="icd-interface-type-input"]'
            ],
            [
                "pierce/[data-testid='icd-interface-type-input']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Vertragsspezifikation'
            ],
            [
                "[data-testid='icd-contract-textarea']"
            ],
            [
                'xpath///*[@data-testid="icd-contract-textarea"]'
            ],
            [
                "pierce/[data-testid='icd-contract-textarea']"
            ]
        ],
        offsetY: 43,
        offsetX: 88,
    });
    await runner.runStep({
        type: 'change',
        value: 'asdfasdf',
        selectors: [
            [
                'aria/Vertragsspezifikation'
            ],
            [
                "[data-testid='icd-contract-textarea']"
            ],
            [
                'xpath///*[@data-testid="icd-contract-textarea"]'
            ],
            [
                "pierce/[data-testid='icd-contract-textarea']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Vorbedingungen'
            ],
            [
                "[data-testid='icd-preconditions-input']"
            ],
            [
                'xpath///*[@data-testid="icd-preconditions-input"]'
            ],
            [
                "pierce/[data-testid='icd-preconditions-input']"
            ]
        ],
        offsetY: 9,
        offsetX: 70,
    });
    await runner.runStep({
        type: 'change',
        value: 'asdf',
        selectors: [
            [
                'aria/Vorbedingungen'
            ],
            [
                "[data-testid='icd-preconditions-input']"
            ],
            [
                'xpath///*[@data-testid="icd-preconditions-input"]'
            ],
            [
                "pierce/[data-testid='icd-preconditions-input']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Nachbedingungen'
            ],
            [
                "[data-testid='icd-postconditions-input']"
            ],
            [
                'xpath///*[@data-testid="icd-postconditions-input"]'
            ],
            [
                "pierce/[data-testid='icd-postconditions-input']"
            ]
        ],
        offsetY: 44,
        offsetX: 62,
    });
    await runner.runStep({
        type: 'change',
        value: 'sadf',
        selectors: [
            [
                'aria/Nachbedingungen'
            ],
            [
                "[data-testid='icd-postconditions-input']"
            ],
            [
                'xpath///*[@data-testid="icd-postconditions-input"]'
            ],
            [
                "pierce/[data-testid='icd-postconditions-input']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Invarianten'
            ],
            [
                "[data-testid='icd-invariants-input']"
            ],
            [
                'xpath///*[@data-testid="icd-invariants-input"]'
            ],
            [
                "pierce/[data-testid='icd-invariants-input']"
            ]
        ],
        offsetY: 20,
        offsetX: 72,
    });
    await runner.runStep({
        type: 'change',
        value: 'asdf',
        selectors: [
            [
                'aria/Invarianten'
            ],
            [
                "[data-testid='icd-invariants-input']"
            ],
            [
                'xpath///*[@data-testid="icd-invariants-input"]'
            ],
            [
                "pierce/[data-testid='icd-invariants-input']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Speichern'
            ],
            [
                "[data-testid='create-icd-submit']"
            ],
            [
                'xpath///*[@data-testid="create-icd-submit"]'
            ],
            [
                "pierce/[data-testid='create-icd-submit']"
            ],
            [
                'text/Speichern'
            ]
        ],
        offsetY: 19,
        offsetX: 59,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Diagramme'
            ],
            [
                'li:nth-of-type(12) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[12]/a'
            ],
            [
                'pierce/li:nth-of-type(12) > a'
            ],
            [
                'text/Diagramme'
            ]
        ],
        offsetY: 12,
        offsetX: 60,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/WK-Context-001: User-System context · v1'
            ],
            [
                "[data-testid='diagram-item-38e8d026-306e-4a18-a7c7-f2d0cd0112d4'] > button:nth-of-type(1)"
            ],
            [
                'xpath///*[@data-testid="diagram-item-38e8d026-306e-4a18-a7c7-f2d0cd0112d4"]/button[1]'
            ],
            [
                "pierce/[data-testid='diagram-item-38e8d026-306e-4a18-a7c7-f2d0cd0112d4'] > button:nth-of-type(1)"
            ],
            [
                'text/WK-Context-001: User-Systemcontext'
            ]
        ],
        offsetY: 18,
        offsetX: 225,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='diagram-source-preview']"
            ],
            [
                'xpath///*[@data-testid="diagram-source-preview"]'
            ],
            [
                "pierce/[data-testid='diagram-source-preview']"
            ]
        ],
        offsetY: 105,
        offsetX: 239,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Löschen'
            ],
            [
                "[data-testid='diagram-delete-btn']"
            ],
            [
                'xpath///*[@data-testid="diagram-delete-btn"]'
            ],
            [
                "pierce/[data-testid='diagram-delete-btn']"
            ],
            [
                'text/Löschen'
            ]
        ],
        offsetY: 17,
        offsetX: 36.515625,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='diagrams-list'] div:nth-of-type(1)"
            ],
            [
                'xpath///*[@data-testid="diagram-item-c32a76a5-19e0-4de5-953f-fd084018022d"]/button[1]/div[1]'
            ],
            [
                "pierce/[data-testid='diagrams-list'] div:nth-of-type(1)"
            ],
            [
                'text/WK-Block-001:'
            ]
        ],
        offsetY: 16,
        offsetX: 63,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Löschen'
            ],
            [
                "[data-testid='diagram-delete-btn']"
            ],
            [
                'xpath///*[@data-testid="diagram-delete-btn"]'
            ],
            [
                "pierce/[data-testid='diagram-delete-btn']"
            ],
            [
                'text/Löschen'
            ]
        ],
        offsetY: 21,
        offsetX: 67.515625,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/SE-Metriken'
            ],
            [
                'li:nth-of-type(13) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[13]/a'
            ],
            [
                'pierce/li:nth-of-type(13) > a'
            ],
            [
                'text/SE-Metriken'
            ]
        ],
        offsetY: 26,
        offsetX: 36,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='metric-tile-volatility']"
            ],
            [
                'xpath///*[@data-testid="metric-tile-volatility"]'
            ],
            [
                "pierce/[data-testid='metric-tile-volatility']"
            ]
        ],
        offsetY: 40,
        offsetX: 186,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='metric-tile-coverage'] > div:nth-of-type(2)"
            ],
            [
                'xpath///*[@data-testid="metric-tile-coverage"]/div[2]'
            ],
            [
                "pierce/[data-testid='metric-tile-coverage'] > div:nth-of-type(2)"
            ],
            [
                'text/0.0%'
            ]
        ],
        offsetY: 15,
        offsetX: 278,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Filter'
            ],
            [
                "[data-testid='metrics-filter-select']"
            ],
            [
                'xpath///*[@data-testid="metrics-filter-select"]'
            ],
            [
                "pierce/[data-testid='metrics-filter-select']"
            ]
        ],
        offsetY: 26,
        offsetX: 68.9375,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Filter'
            ],
            [
                "[data-testid='metrics-filter-select']"
            ],
            [
                'xpath///*[@data-testid="metrics-filter-select"]'
            ],
            [
                "pierce/[data-testid='metrics-filter-select']"
            ]
        ],
        offsetY: 10,
        offsetX: 72.9375,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='metric-tile-volatility'] > div:nth-of-type(1) > span:nth-of-type(1)"
            ],
            [
                'xpath///*[@data-testid="metric-tile-volatility"]/div[1]/span[1]'
            ],
            [
                "pierce/[data-testid='metric-tile-volatility'] > div:nth-of-type(1) > span:nth-of-type(1)"
            ]
        ],
        offsetY: 3,
        offsetX: 65,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='metrics-dashboard']"
            ],
            [
                'xpath///*[@data-testid="metrics-dashboard"]'
            ],
            [
                "pierce/[data-testid='metrics-dashboard']"
            ]
        ],
        offsetY: 33,
        offsetX: 472,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Filter'
            ],
            [
                "[data-testid='metrics-filter-select']"
            ],
            [
                'xpath///*[@data-testid="metrics-filter-select"]'
            ],
            [
                "pierce/[data-testid='metrics-filter-select']"
            ]
        ],
        offsetY: 8,
        offsetX: 56.9375,
    });
    await runner.runStep({
        type: 'change',
        value: 'volatility',
        selectors: [
            [
                'aria/Filter'
            ],
            [
                "[data-testid='metrics-filter-select']"
            ],
            [
                'xpath///*[@data-testid="metrics-filter-select"]'
            ],
            [
                "pierce/[data-testid='metrics-filter-select']"
            ]
        ],
        target: 'main'
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Aktualisieren'
            ],
            [
                "[data-testid='metrics-refresh-btn']"
            ],
            [
                'xpath///*[@data-testid="metrics-refresh-btn"]'
            ],
            [
                "pierce/[data-testid='metrics-refresh-btn']"
            ],
            [
                'text/Aktualisieren'
            ]
        ],
        offsetY: 7,
        offsetX: 50.9375,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Workspace-Einstellungen'
            ],
            [
                'li:nth-of-type(14) > a'
            ],
            [
                'xpath///*[@id="root"]/div/nav/ul/li[14]/a'
            ],
            [
                'pierce/li:nth-of-type(14) > a'
            ],
            [
                'text/Workspace-Einstellungen'
            ]
        ],
        offsetY: 30,
        offsetX: 52,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Standard Baselines: ✓  |  change_reason: optional  | Full (Draft/Approved/Deprecated)'
            ],
            [
                "[data-testid='preset-option-standard']"
            ],
            [
                'xpath///*[@data-testid="preset-option-standard"]'
            ],
            [
                "pierce/[data-testid='preset-option-standard']"
            ]
        ],
        offsetY: 7.59375,
        offsetX: 7,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Extended Baselines: ✓  |  change_reason: required  | Full + Approval workflow'
            ],
            [
                "[data-testid='preset-option-extended']"
            ],
            [
                'xpath///*[@data-testid="preset-option-extended"]'
            ],
            [
                "pierce/[data-testid='preset-option-extended']"
            ]
        ],
        offsetY: 10.59375,
        offsetX: 6,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Risks(aus Preset)'
            ],
            [
                "[data-testid='visibility-checkbox-risk']"
            ],
            [
                'xpath///*[@data-testid="visibility-checkbox-risk"]'
            ],
            [
                "pierce/[data-testid='visibility-checkbox-risk']"
            ]
        ],
        offsetY: 0.09375,
        offsetX: 4,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/ADR (Architecture Decision Records)(aus Preset)'
            ],
            [
                "[data-testid='visibility-checkbox-adr']"
            ],
            [
                'xpath///*[@data-testid="visibility-checkbox-adr"]'
            ],
            [
                "pierce/[data-testid='visibility-checkbox-adr']"
            ]
        ],
        offsetY: 2.09375,
        offsetX: 7,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='visibility-row-icds'] > label"
            ],
            [
                'xpath///*[@data-testid="visibility-row-icds"]/label'
            ],
            [
                "pierce/[data-testid='visibility-row-icds'] > label"
            ]
        ],
        offsetY: 6.59375,
        offsetX: 2,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Diagrams(überschrieben)'
            ],
            [
                "[data-testid='visibility-checkbox-diagrams']"
            ],
            [
                'xpath///*[@data-testid="visibility-checkbox-diagrams"]'
            ],
            [
                "pierce/[data-testid='visibility-checkbox-diagrams']"
            ]
        ],
        offsetY: 10.59375,
        offsetX: 1,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Issues(aus Preset)'
            ],
            [
                "[data-testid='visibility-checkbox-issue']"
            ],
            [
                'xpath///*[@data-testid="visibility-checkbox-issue"]'
            ],
            [
                "pierce/[data-testid='visibility-checkbox-issue']"
            ]
        ],
        offsetY: 3.09375,
        offsetX: 10,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                "[data-testid='visibility-row-icds'] > label"
            ],
            [
                'xpath///*[@data-testid="visibility-row-icds"]/label'
            ],
            [
                "pierce/[data-testid='visibility-row-icds'] > label"
            ]
        ],
        offsetY: 1.59375,
        offsetX: 13,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Diagrams(überschrieben)'
            ],
            [
                "[data-testid='visibility-checkbox-diagrams']"
            ],
            [
                'xpath///*[@data-testid="visibility-checkbox-diagrams"]'
            ],
            [
                "pierce/[data-testid='visibility-checkbox-diagrams']"
            ]
        ],
        offsetY: 11.59375,
        offsetX: 7,
    });
    await runner.runStep({
        type: 'click',
        target: 'main',
        selectors: [
            [
                'aria/Issues(überschrieben)'
            ],
            [
                "[data-testid='visibility-checkbox-issue']"
            ],
            [
                'xpath///*[@data-testid="visibility-checkbox-issue"]'
            ],
            [
                "pierce/[data-testid='visibility-checkbox-issue']"
            ]
        ],
        offsetY: 7.59375,
        offsetX: 5,
    });

    await runner.runAfterAllSteps();
}

if (process && import.meta.url === url.pathToFileURL(process.argv[1]).href) {
    run()
}
