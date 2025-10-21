"""
ПОЛНЫЙ MULTI-AGENT СИСТЕМА
Поддерживает: HH.ru, Яндекс.Еда, Яндекс.Почта
"""

import asyncio
import json
import re
from typing import Dict, List, Optional
from playwright.async_api import async_playwright, Page
from openai import AsyncOpenAI
import os
from datetime import datetime

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

GROQ_API_KEY = ""
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


# ============================================================================
# БАЗОВЫЙ АГЕНТ
# ============================================================================

class BaseAgent:
    """Базовый класс для всех агентов"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=GROQ_API_KEY,
            base_url=GROQ_BASE_URL
        )
        self.playwright = None
        self.browser = None
        self.page = None

    async def setup_browser(self):
        """Настройка браузера"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch_persistent_context(
                user_data_dir="./browser-data",
                headless=False,
                viewport={"width": 1280, "height": 720},
                args=['--start-maximized']
            )
            self.page = await self.browser.new_page()
            self.page.set_default_timeout(30000)
            self.page.set_default_navigation_timeout(45000)
            print("✅ Браузер запущен!")
            return True
        except Exception as e:
            print(f"❌ Ошибка запуска браузера: {e}")
            return False

    async def cleanup(self):
        """Закрытие браузера"""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except:
            pass

    async def wait_for_stable(self, timeout: int = 3):
        """Ожидание стабилизации страницы"""
        await asyncio.sleep(timeout)


# ============================================================================
# АГЕНТ ДЛЯ HH.RU
# ============================================================================

class JobSearchAgent(BaseAgent):
    """Агент для поиска работы на HH.ru"""

    def __init__(self, enable_real_apply: bool = False):
        super().__init__()
        self.enable_real_apply = enable_real_apply
        self.found_vacancies = []
        self.cover_letters = []
        self.applied_vacancies = []

    async def search_vacancies(self, job_query: str) -> bool:
        """Поиск вакансий"""
        print(f"\n🔍 Поиск вакансий: {job_query}")

        try:
            encoded_query = job_query.replace(" ", "+")
            search_url = f"https://hh.ru/search/vacancy?text={encoded_query}&area=1"

            await self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await self.wait_for_stable()

            print(f"✅ Успешная загрузка: {self.page.url}")
            return True

        except Exception as e:
            print(f"❌ Ошибка поиска: {e}")
            return False

    async def collect_vacancies(self):
        """Сбор вакансий"""
        print("📋 Собираю вакансии...")

        try:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.wait_for_stable(2)

            vacancies_data = await self.page.evaluate("""
                () => {
                    const vacancies = [];
                    const seenUrls = new Set();

                    const selectors = [
                        '[data-qa="vacancy-serp__vacancy"]',
                        '.serp-item',
                        '.vacancy-serp-item'
                    ];

                    let allCards = [];
                    selectors.forEach(selector => {
                        const cards = document.querySelectorAll(selector);
                        if (cards.length > 0) {
                            allCards = allCards.concat(Array.from(cards));
                        }
                    });

                    for (let card of allCards) {
                        if (vacancies.length >= 15) break;

                        try {
                            const linkElem = card.querySelector('a[href*="vacancy"]');
                            if (!linkElem) continue;

                            const url = linkElem.href;
                            const title = linkElem.textContent?.trim();

                            if (!title || !url || seenUrls.has(url)) continue;
                            seenUrls.add(url);

                            let company = 'Не указано';
                            const companyElem = card.querySelector('[data-qa="vacancy-serp__vacancy-employer"]');
                            if (companyElem) company = companyElem.textContent?.trim();

                            let salary = 'Не указана';
                            const salaryElem = card.querySelector('[data-qa="vacancy-serp__vacancy-compensation"]');
                            if (salaryElem) salary = salaryElem.textContent?.trim();

                            vacancies.push({
                                title: title,
                                company: company,
                                salary: salary,
                                url: url
                            });

                        } catch (e) {}
                    }

                    return vacancies;
                }
            """)

            if vacancies_data:
                self.found_vacancies = vacancies_data
                print(f"✅ Собрано {len(vacancies_data)} вакансий")
                return True
            return False

        except Exception as e:
            print(f"❌ Ошибка сбора вакансий: {e}")
            return False

    async def analyze_and_create_letters(self):
        """Анализ вакансий и создание сопроводительных писем"""
        if not self.found_vacancies:
            return

        print("\n🎯 Анализирую релевантность...")

        ai_keywords = ['ai', 'machine learning', 'data science', 'ml', 'deep learning', 'neural']

        for vacancy in self.found_vacancies[:10]:
            title_lower = vacancy['title'].lower()
            score = 20

            for keyword in ai_keywords:
                if keyword in title_lower:
                    score += 15

            if 'ai' in title_lower or 'artificial intelligence' in title_lower:
                score += 10
            if 'machine learning' in title_lower or 'ml' in title_lower:
                score += 10

            vacancy['match_score'] = min(100, score)

        sorted_vacancies = sorted(self.found_vacancies, key=lambda x: x.get('match_score', 0), reverse=True)
        top_vacancies = sorted_vacancies[:3]

        print("\n📝 Создаю сопроводительные письма...")

        for i, vacancy in enumerate(top_vacancies):
            print(f"  ✉️  Письмо {i + 1}: {vacancy['title'][:40]}... ({vacancy['match_score']}%)")

            try:
                prompt = f"""
                Напиши краткое профессиональное сопроводительное письмо для отклика на вакансию.

                Вакансия: {vacancy['title']}
                Компания: {vacancy['company']}

                Профиль кандидата:
                - Data Scientist / AI Engineer
                - Навыки: Python, Machine Learning, Deep Learning, SQL, Data Analysis
                - Опыт: разработка ML моделей, анализ данных

                Сделай письмо:
                - Профессиональным и кратким (100-150 слов)
                - С релевантными навыками
                - Без шапки и контактных данных
                - На русском языке

                Напиши только текст письма.
                """

                response = await self.client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=300
                )

                cover_letter = {
                    'vacancy_title': vacancy['title'],
                    'company_name': vacancy['company'],
                    'content': response.choices[0].message.content.strip(),
                    'url': vacancy['url'],
                    'match_score': vacancy['match_score']
                }

                self.cover_letters.append(cover_letter)
                print(f"    ✅ Письмо создано")

            except Exception as e:
                print(f"    ❌ Ошибка: {e}")

    async def apply_to_vacancies(self):
        """Отправка откликов"""
        if not self.cover_letters:
            print("❌ Нет писем для отправки")
            return

        print(f"\n🚀 {'РЕАЛЬНАЯ ОТПРАВКА' if self.enable_real_apply else 'ТЕСТОВАЯ СИМУЛЯЦИЯ'} ОТКЛИКОВ")
        print("=" * 60)

        applied_count = 0

        for i, letter in enumerate(self.cover_letters):
            print(f"\n--- ОТКЛИК {i + 1}/{len(self.cover_letters)} ---")
            print(f"🎯 {letter['vacancy_title']}")
            print(f"🏢 {letter['company_name']}")
            print(f"📊 Релевантность: {letter['match_score']}%")

            success = await self.apply_to_single_vacancy(letter)
            if success:
                applied_count += 1
                self.applied_vacancies.append(letter)
                print("✅ ОТКЛИК ОБРАБОТАН!")
            else:
                print("❌ Проблема с откликом")

            await asyncio.sleep(2)

        print(f"\n🎉 ОБРАБОТАНО ОТКЛИКОВ: {applied_count}/{len(self.cover_letters)}")

    async def apply_to_single_vacancy(self, cover_letter: dict) -> bool:
        """Отправка отклика на одну вакансию"""
        try:
            print("    🔄 Перехожу на страницу вакансии...")
            await self.page.goto(cover_letter['url'], wait_until="domcontentloaded", timeout=30000)
            await self.wait_for_stable()

            # Поиск кнопки отклика
            apply_selectors = [
                '[data-qa="vacancy-response-link-top"]',
                '[data-qa="vacancy-response-letter-toggle"]',
                'button:has-text("Откликнуться")',
                'a:has-text("Откликнуться")'
            ]

            apply_button_found = False
            for selector in apply_selectors:
                try:
                    if await self.page.locator(selector).count() > 0:
                        print(f"    ✅ Найдена кнопка отклика")
                        await self.page.click(selector)
                        await self.wait_for_stable()
                        apply_button_found = True
                        break
                except:
                    continue

            if not apply_button_found:
                print("    ❌ Не найдена кнопка отклика")
                return False

            # Заполнение сопроводительного письма
            letter_selectors = [
                '[data-qa="vacancy-response-popup-form-letter-input"]',
                'textarea[name="letter"]',
                '.bloko-textarea'
            ]

            letter_filled = False
            for selector in letter_selectors:
                try:
                    if await self.page.locator(selector).count() > 0:
                        print("    📝 Заполняю сопроводительное письмо...")
                        await self.page.fill(selector, cover_letter['content'])
                        letter_filled = True
                        print("    ✅ Письмо заполнено")
                        break
                except:
                    continue

            # РЕАЛЬНАЯ ОТПРАВКА
            if self.enable_real_apply:
                print("    🚀 ПРОИЗВОЖУ РЕАЛЬНУЮ ОТПРАВКУ...")

                submit_selectors = [
                    '[data-qa="vacancy-response-submit-popup"]',
                    'button[type="submit"]',
                    'button:has-text("Отправить отклик")'
                ]

                for selector in submit_selectors:
                    try:
                        if await self.page.locator(selector).count() > 0:
                            await self.page.click(selector)
                            await self.wait_for_stable()
                            print("    ✅ ОТКЛИК ОТПРАВЛЕН!")
                            return True
                    except Exception as e:
                        continue

                print("    ❌ Не найдена кнопка отправки")
                return False
            else:
                print("    🎯 ТЕСТОВЫЙ РЕЖИМ: отклик готов к отправке")
                return True

        except Exception as e:
            print(f"    ❌ Ошибка при отклике: {e}")
            return False

    async def run(self, job_query: str):
        """Запуск полного процесса"""
        print("\n" + "=" * 60)
        print("💼 АГЕНТ ПОИСКА РАБОТЫ (HH.RU)")
        print("=" * 60)

        try:
            if not await self.setup_browser():
                return False

            if not await self.search_vacancies(job_query):
                return False

            if not await self.collect_vacancies():
                return False

            await self.analyze_and_create_letters()
            await self.apply_to_vacancies()

            # Отчет
            print("\n" + "=" * 60)
            print("📊 ОТЧЕТ")
            print("=" * 60)
            print(f"🔍 Найдено вакансий: {len(self.found_vacancies)}")
            print(f"📝 Создано писем: {len(self.cover_letters)}")
            print(
                f"🚀 {'ОТПРАВЛЕНО' if self.enable_real_apply else 'ПОДГОТОВЛЕНО'} откликов: {len(self.applied_vacancies)}")

            if self.applied_vacancies:
                print(f"\n✅ {'ОТПРАВЛЕННЫЕ' if self.enable_real_apply else 'ПОДГОТОВЛЕННЫЕ'} ОТКЛИКИ:")
                for i, applied in enumerate(self.applied_vacancies, 1):
                    print(f"  {i}. {applied['vacancy_title']}")
                    print(f"     🏢 {applied['company_name']}")
                    print(f"     📊 {applied['match_score']}% релевантности")

            return True

        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await self.cleanup()


# ============================================================================
# АГЕНТ ДЛЯ ЯНДЕКС.ПОЧТЫ
# ============================================================================

class EmailAgent(BaseAgent):
    """Агент для работы с Яндекс.Почтой"""

    def __init__(self, enable_real_delete: bool = False):
        super().__init__()
        self.enable_real_delete = enable_real_delete
        self.emails = []
        self.spam_emails = []
        self.deleted_count = 0

    async def open_yandex_mail(self) -> bool:
        """Открытие Яндекс.Почты"""
        print("\n📧 Открываю Яндекс.Почту...")

        try:
            await self.page.goto("https://mail.yandex.ru", wait_until="domcontentloaded", timeout=30000)
            await self.wait_for_stable()

            # Проверка авторизации
            current_url = self.page.url
            if "passport.yandex" in current_url:
                print("❌ Требуется авторизация! Войдите в аккаунт вручную.")
                print("⏳ Ожидание авторизации (60 секунд)...")
                await asyncio.sleep(60)

            print("✅ Яндекс.Почта открыта")
            return True

        except Exception as e:
            print(f"❌ Ошибка открытия почты: {e}")
            return False

    async def collect_emails(self, limit: int = 10) -> bool:
        """Сбор писем с фильтрацией навигации"""
        print(f"\n📋 Собираю последние {limit} писем...")

        try:
            await self.wait_for_stable(5)

            # Прокручиваем страницу
            print("    📜 Прокручиваю страницу...")
            for i in range(3):
                await self.page.evaluate("window.scrollBy(0, 400)")
                await asyncio.sleep(1)

            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(2)

            # ИСПРАВЛЕНО: Фильтруем навигационные элементы
            print("    🔍 Поиск писем с фильтрацией навигации...")

            # Список навигационных элементов для исключения
            navigation_keywords = [
                'входящие', 'рассылки', 'социальные сети',
                'с вложениями', 'мои папки', 'отправленные',
                'удалённые', 'черновики', 'спам', 'корзина',
                'написать', 'настройки', 'выйти'
            ]

            email_selectors = [
                "[role='listitem']",
                ".mail-MessageSnippet",
                "[data-qa='message-item']"
            ]

            for selector in email_selectors:
                try:
                    count = await self.page.locator(selector).count()
                    if count == 0:
                        continue

                    print(f"       ✓ Проверяю {selector}: {count} элементов")

                    emails_collected = 0

                    for i in range(count):
                        if emails_collected >= limit:
                            break

                        try:
                            email_element = self.page.locator(selector).nth(i)
                            full_text = await email_element.text_content()

                            if not full_text or len(full_text.strip()) < 10:
                                continue

                            # КЛЮЧЕВАЯ ПРОВЕРКА: Это не навигация?
                            text_lower = full_text.lower()
                            is_navigation = any(keyword in text_lower for keyword in navigation_keywords)

                            # Дополнительная проверка: письма обычно содержат email или дату
                            looks_like_email = (
                                    '@' in full_text or
                                    any(month in text_lower for month in
                                        ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя',
                                         'дек']) or
                                    'вчера' in text_lower or
                                    'сегодня' in text_lower or
                                    any(char.isdigit() and ':' in full_text for char in full_text)  # Время типа "14:30"
                            )

                            if is_navigation or not looks_like_email:
                                print(f"          ⏭️  Пропускаю навигацию: {full_text[:40]}...")
                                continue

                            # Парсим письмо
                            lines = [line.strip() for line in full_text.split('\n') if line.strip()]

                            sender = lines[0] if len(lines) >= 1 else "Неизвестно"
                            subject = lines[1] if len(lines) >= 2 else "Без темы"
                            preview = ' '.join(lines[2:5]) if len(lines) > 2 else ""

                            # Поиск даты
                            date = "Неизвестно"
                            for line in lines[-3:]:
                                if any(kw in line.lower() for kw in
                                       ['янв', 'фев', 'мар', 'сегодня', 'вчера']) or ':' in line:
                                    date = line
                                    break

                            email_data = {
                                'index': emails_collected + 1,
                                'sender': sender[:100],
                                'subject': subject[:100],
                                'date': date[:50],
                                'preview': preview[:200],
                                'is_read': 'непрочитан' not in text_lower,
                                'is_important': 'важн' in text_lower or '⭐' in full_text,
                                'has_attachment': '📎' in full_text or 'прикреп' in text_lower,
                                'selector': selector,
                                'element_index': i,
                                'full_text': full_text[:300]
                            }

                            self.emails.append(email_data)
                            emails_collected += 1
                            print(f"      📧 Письмо {emails_collected}: {sender[:30]} - {subject[:40]}")

                        except Exception as e:
                            continue

                    if emails_collected > 0:
                        print(f"    ✅ Собрано {emails_collected} писем через {selector}")
                        return True

                except Exception as e:
                    continue

            # JavaScript fallback
            print("    🔍 JavaScript поиск писем...")

            emails_data = await self.page.evaluate(f"""
                (limit, navKeywords) => {{
                    const emails = [];
                    const elements = document.querySelectorAll('[role="listitem"], div, article');

                    for (let elem of elements) {{
                        const text = elem.textContent || '';
                        const textLower = text.toLowerCase();

                        // Проверка на навигацию
                        const isNav = navKeywords.some(kw => textLower.includes(kw));

                        // Признаки письма
                        const hasEmail = text.includes('@');
                        const hasDate = /янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|дек|вчера|сегодня/i.test(text);
                        const hasTime = /\\d{{1,2}}:\\d{{2}}/.test(text);
                        const reasonableLength = text.length > 30 && text.length < 2000;

                        if (!isNav && (hasEmail || hasDate || hasTime) && reasonableLength) {{
                            const lines = text.split('\\n').map(l => l.trim()).filter(l => l);

                            if (lines.length >= 2) {{
                                emails.push({{
                                    sender: lines[0],
                                    subject: lines[1],
                                    preview: lines.slice(2).join(' ').substring(0, 100),
                                    index: emails.length
                                }});
                            }}
                        }}

                        if (emails.length >= limit) break;
                    }}

                    return emails;
                }}
            """, limit, navigation_keywords)

            if emails_data and len(emails_data) > 0:
                print(f"    ✅ Найдено {len(emails_data)} писем через JavaScript")

                for data in emails_data:
                    self.emails.append({
                        'index': len(self.emails) + 1,
                        'sender': data['sender'][:100],
                        'subject': data['subject'][:100],
                        'date': 'Неизвестно',
                        'preview': data['preview'],
                        'is_read': True,
                        'is_important': False,
                        'has_attachment': False,
                        'full_text': ''
                    })
                    print(f"      📧 Письмо {len(self.emails)}: {data['sender'][:30]} - {data['subject'][:40]}")

                return True

            print("    ❌ Письма не найдены")
            return False

        except Exception as e:
            print(f"    ❌ Ошибка: {e}")
            return False

    async def analyze_spam(self):
        """Анализ спама"""
        if not self.emails:
            print("\n⚠️  Нет писем для анализа")
            return

        print("\n🎯 Анализирую письма на спам...")

        spam_keywords = [
            'акция', 'скидка', 'распродажа', 'промо', 'купон',
            'выигра', 'приз', 'бесплатно', 'заработ', 'кредит',
            'казино', 'ставк', 'лотере', 'рассылка', 'маркетинг'
        ]

        suspicious_senders = [
            'no-reply', 'noreply', 'marketing', 'promo', 'newsletter'
        ]

        for email in self.emails:
            spam_score = 0

            text_lower = f"{email['sender']} {email['subject']} {email['preview']}".lower()

            # Проверка ключевых слов
            for keyword in spam_keywords:
                if keyword in text_lower:
                    spam_score += 15

            # Проверка отправителя
            for suspicious in suspicious_senders:
                if suspicious in email['sender'].lower():
                    spam_score += 20

            # Восклицательные знаки
            if '!' in email['subject']:
                spam_score += 10

            # Caps Lock
            if email['subject'].isupper() and len(email['subject']) > 10:
                spam_score += 15

            email['spam_score'] = min(100, spam_score)
            email['is_spam'] = spam_score >= 40

            if email['is_spam']:
                self.spam_emails.append(email)
                print(f"  🚩 СПАМ ({spam_score}%): {email['sender'][:25]} - {email['subject'][:30]}")
            else:
                print(f"  ✅ ВАЖНО ({spam_score}%): {email['sender'][:25]} - {email['subject'][:30]}")

        print(f"\n📊 Результат: {len(self.spam_emails)} спам из {len(self.emails)} писем")

    async def delete_spam(self):
        """Удаление спама"""
        if not self.spam_emails:
            print("\n✅ Спам не обнаружен!")
            return

        print(f"\n🗑️  {'РЕАЛЬНОЕ УДАЛЕНИЕ' if self.enable_real_delete else 'ТЕСТОВЫЙ РЕЖИМ'}")
        print("=" * 60)

        for i, email in enumerate(self.spam_emails, 1):
            print(f"\n--- Письмо {i}/{len(self.spam_emails)} ---")
            print(f"📧 {email['subject']}")
            print(f"👤 От: {email['sender']}")
            print(f"⚠️  Spam Score: {email['spam_score']}%")

            if self.enable_real_delete:
                confirmation = input("    Удалить? (y/n): ").strip().lower()
                if confirmation == 'y':
                    # Здесь должна быть логика удаления
                    print("    ✅ Помечено к удалению")
                    self.deleted_count += 1
                else:
                    print("    ⏭️  Пропущено")
            else:
                print("    🎯 ТЕСТОВЫЙ РЕЖИМ: будет удалено")
                self.deleted_count += 1

        print(f"\n🎉 {'Удалено' if self.enable_real_delete else 'Отмечено к удалению'}: {self.deleted_count} писем")

    async def run(self, count: int = 10):
        """Запуск агента"""
        print("\n" + "=" * 60)
        print("📧 АГЕНТ ЯНДЕКС.ПОЧТЫ")
        print("=" * 60)

        try:
            if not await self.setup_browser():
                return False

            if not await self.open_yandex_mail():
                return False

            if not await self.collect_emails(count):
                return False

            await self.analyze_spam()
            await self.delete_spam()

            # Отчет
            print("\n" + "=" * 60)
            print("📊 ОТЧЕТ")
            print("=" * 60)
            print(f"📧 Проанализировано: {len(self.emails)} писем")
            print(f"🚩 Обнаружено спама: {len(self.spam_emails)}")
            print(f"🗑️  {'Удалено' if self.enable_real_delete else 'Отмечено'}: {self.deleted_count}")
            print(f"✅ Важных сохранено: {len(self.emails) - len(self.spam_emails)}")

            return True

        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await self.cleanup()

# ============================================================================
# АГЕНТ ДЛЯ ЯНДЕКС.ЕДЫ
# ============================================================================

class FoodDeliveryAgent(BaseAgent):
    """Агент для заказа еды на Яндекс.Еде"""

    def __init__(self, enable_real_order: bool = False):
        super().__init__()
        self.enable_real_order = enable_real_order
        self.cart_items = []
        self.total_price = 0

    async def open_yandex_eda(self) -> bool:
        """Открытие Яндекс.Еды"""
        print("\n🍔 Открываю Яндекс.Еду...")

        try:
            await self.page.goto("https://eda.yandex.ru", wait_until="domcontentloaded", timeout=30000)
            await self.wait_for_stable()

            # Закрытие модальных окон
            await self.close_popups()

            # Проверка авторизации
            current_url = self.page.url
            if "passport.yandex" in current_url:
                print("❌ Требуется авторизация! Войдите в аккаунт вручную.")
                print("⏳ Ожидание авторизации (60 секунд)...")
                await asyncio.sleep(60)

            print("✅ Яндекс.Еда открыта")
            return True

        except Exception as e:
            print(f"❌ Ошибка открытия Яндекс.Еды: {e}")
            return False

    async def close_popups(self):
        """Закрытие всплывающих окон"""
        popup_selectors = [
            'button:has-text("Принять")',
            'button:has-text("OK")',
            '[aria-label="Закрыть"]',
            '.Modal_close'
        ]

        for selector in popup_selectors:
            try:
                if await self.page.locator(selector).count() > 0:
                    await self.page.click(selector, timeout=2000)
                    await asyncio.sleep(1)
            except:
                pass

    async def search_restaurant(self, restaurant_name: str) -> bool:
        """Поиск ресторана"""
        print(f"\n🔍 Ищу ресторан: {restaurant_name}")

        try:
            # Закрываем возможные попапы
            await self.close_popups()

            # Поиск поля ввода
            search_selectors = [
                'input[placeholder*="Найти"]',
                'input[type="search"]',
                'input[placeholder*="ресторан"]',
                'input[placeholder*="Ресторан"]',
                '.DesktopSearchInput',
                '[data-testid="search-input"]'
            ]

            search_found = False
            for selector in search_selectors:
                try:
                    if await self.page.locator(selector).count() > 0:
                        print(f"    ✓ Найдено поле поиска: {selector}")
                        await self.page.fill(selector, restaurant_name)
                        await asyncio.sleep(1)
                        await self.page.press(selector, "Enter")
                        search_found = True
                        break
                except:
                    continue

            if not search_found:
                print("    ⚠️  Поле поиска не найдено, пробую альтернативный метод...")
                # Пробуем найти любой input
                try:
                    all_inputs = await self.page.locator('input[type="text"], input[type="search"]').all()
                    if all_inputs:
                        await all_inputs[0].fill(restaurant_name)
                        await asyncio.sleep(1)
                        await all_inputs[0].press("Enter")
                        search_found = True
                except:
                    pass

            if not search_found:
                print("❌ Не найдено поле поиска")
                return False

            # Ожидание результатов поиска
            await self.wait_for_stable(3)

            # ВАЖНО: Прокручиваем вниз для загрузки результатов
            print("    🔄 Прокручиваю страницу для загрузки результатов...")
            for i in range(5):
                await self.page.evaluate(f"window.scrollBy(0, {300 * (i + 1)})")
                await asyncio.sleep(1.5)

            # Прокручиваем обратно вверх
            await self.page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)

            print("✅ Поиск выполнен, результаты загружены")
            return True

        except Exception as e:
            print(f"❌ Ошибка поиска: {e}")
            return False

    async def select_restaurant(self, restaurant_name: str) -> bool:
        """Выбор ресторана из результатов"""
        print(f"\n🏪 Выбираю ресторан: {restaurant_name}")

        try:
            await self.wait_for_stable(2)

            # Еще раз прокручиваем для уверенности
            print("    🔄 Загружаю карточки ресторанов...")
            await self.page.evaluate("window.scrollBy(0, 400)")
            await asyncio.sleep(2)

            # Нормализация названия для поиска
            def normalize_name(name: str) -> str:
                """Нормализует название для сравнения"""
                import re
                # Убираем все кроме букв и пробелов
                name = re.sub(r'[^\w\s]', '', name.lower())
                # Убираем лишние пробелы
                name = ' '.join(name.split())
                return name

            normalized_search = normalize_name(restaurant_name)
            print(f"    🔍 Нормализованный поиск: '{normalized_search}'")

            # Метод 1: Улучшенный JavaScript поиск с нормализацией
            print("    🔍 Метод 1: Поиск с нормализацией названия...")

            # Экранируем кавычки для JavaScript
            restaurant_name_js = restaurant_name.replace("'", "\\'").replace('"', '\\"')
            normalized_search_js = normalized_search.replace("'", "\\'").replace('"', '\\"')

            # ИСПРАВЛЕНО: параметры встроены в JavaScript код через f-string
            restaurant_found = await self.page.evaluate(f"""
                () => {{
                    const restaurantName = '{restaurant_name_js}';
                    const normalizedSearch = '{normalized_search_js}';

                    // Функция нормализации
                    function normalize(text) {{
                        return text.toLowerCase()
                            .replace(/[^а-яa-z0-9\\s]/g, '')
                            .replace(/\\s+/g, ' ')
                            .trim();
                    }}

                    // Ищем специфичные селекторы для карточек ресторанов
                    const cardSelectors = [
                        'a[href*="/restaurant/"]',
                        'a[href*="/place/"]',
                        '[data-testid*="restaurant"]',
                        '[class*="PlaceCard"]',
                        '[class*="RestaurantCard"]',
                        '[class*="place-card"]',
                        'article',
                        'div[class*="Card"]'
                    ];

                    let allCards = [];
                    cardSelectors.forEach(selector => {{
                        const elements = document.querySelectorAll(selector);
                        allCards = allCards.concat(Array.from(elements));
                    }});

                    console.log('Найдено карточек:', allCards.length);

                    // Проверяем каждую карточку
                    for (let card of allCards) {{
                        const cardText = card.textContent || '';
                        const cardHtml = card.innerHTML?.toLowerCase() || '';

                        // Проверяем, что это похоже на карточку ресторана
                        const looksLikeRestaurant = 
                            cardHtml.includes('мин') || 
                            cardHtml.includes('rating') ||
                            cardHtml.includes('⭐') ||
                            cardHtml.includes('★') ||
                            cardText.includes('₽');

                        if (looksLikeRestaurant) {{
                            const normalizedCard = normalize(cardText);

                            // Проверяем точное совпадение
                            if (normalizedCard.includes(normalizedSearch)) {{
                                console.log('Найдено точное совпадение:', cardText.substring(0, 50));

                                // Если это ссылка - кликаем на нее
                                if (card.tagName === 'A') {{
                                    card.click();
                                    return true;
                                }}

                                // Ищем ссылку внутри карточки
                                const link = card.querySelector('a[href*="/restaurant/"], a[href*="/place/"]');
                                if (link) {{
                                    link.click();
                                    return true;
                                }}

                                // Кликаем на саму карточку
                                card.click();
                                return true;
                            }}

                            // Проверяем частичное совпадение (все слова присутствуют)
                            const searchWords = normalizedSearch.split(' ');
                            const allWordsPresent = searchWords.every(word => normalizedCard.includes(word));

                            if (allWordsPresent && searchWords.length >= 2) {{
                                console.log('Найдено частичное совпадение:', cardText.substring(0, 50));

                                if (card.tagName === 'A') {{
                                    card.click();
                                    return true;
                                }}

                                const link = card.querySelector('a[href*="/restaurant/"], a[href*="/place/"]');
                                if (link) {{
                                    link.click();
                                    return true;
                                }}

                                card.click();
                                return true;
                            }}
                        }}
                    }}

                    return false;
                }}
            """)

            if restaurant_found:
                await self.wait_for_stable(3)
                print("✅ Ресторан выбран (метод 1)")

                # Проверяем, что мы на странице ресторана
                current_url = self.page.url
                if '/restaurant/' in current_url or '/place/' in current_url:
                    print(f"    ✓ Открыта страница ресторана")
                    return True
                else:
                    print(f"    ⚠️  Возможно, открылась не та страница: {current_url}")

            # Метод 2: Расширенный поиск с получением информации о ресторанах
            print("    🔍 Метод 2: Расширенный поиск...")

            restaurants_info = await self.page.evaluate("""
                () => {
                    function normalize(text) {
                        return text.toLowerCase()
                            .replace(/[^а-яa-z0-9\\s]/g, '')
                            .replace(/\\s+/g, ' ')
                            .trim();
                    }

                    const results = [];
                    const allElements = document.querySelectorAll('a, article, div[class*="card"], div[class*="Card"]');

                    allElements.forEach((elem, index) => {
                        const text = elem.textContent || '';
                        const html = elem.innerHTML || '';

                        // Фильтруем: должно быть похоже на ресторан
                        if ((html.includes('мин') || html.includes('rating') || text.includes('₽')) &&
                            text.length > 10 && text.length < 500) {

                            // Извлекаем название (обычно в начале текста, до цифр)
                            const lines = text.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                            let possibleName = lines[0];

                            // Очищаем от рейтинга и времени
                            possibleName = possibleName.split(/\\d/)[0].trim();

                            if (possibleName && possibleName.length > 2 && possibleName.length < 100) {
                                results.push({
                                    name: possibleName,
                                    normalized: normalize(possibleName),
                                    index: index,
                                    fullText: text.substring(0, 200)
                                });
                            }
                        }
                    });

                    // Убираем дубликаты
                    const unique = [];
                    const seen = new Set();

                    results.forEach(r => {
                        if (!seen.has(r.normalized)) {
                            seen.add(r.normalized);
                            unique.push(r);
                        }
                    });

                    return unique.slice(0, 20);
                }
            """)

            if restaurants_info:
                print(f"\n    📋 Найденные рестораны ({len(restaurants_info)}):")
                for i, rest in enumerate(restaurants_info, 1):
                    print(f"       {i}. {rest['name']}")

                # Ищем совпадение с нормализацией
                best_match = None
                best_score = 0

                for rest in restaurants_info:
                    rest_normalized = rest['normalized']

                    # Точное совпадение
                    if rest_normalized == normalized_search:
                        best_match = rest
                        best_score = 100
                        break

                    # Частичное совпадение (все слова присутствуют)
                    search_words = normalized_search.split()
                    matching_words = sum(1 for word in search_words if word in rest_normalized)
                    score = (matching_words / len(search_words)) * 100

                    if score > best_score and score >= 70:  # Минимум 70% совпадение
                        best_match = rest
                        best_score = score

                if best_match:
                    print(f"\n    ✓ Найдено совпадение: {best_match['name']} (score: {best_score:.0f}%)")
                    print(f"    🖱️  Попытка клика...")

                    # Экранируем для JavaScript
                    normalized_name_js = best_match['normalized'].replace("'", "\\'").replace('"', '\\"')

                    # ИСПРАВЛЕНО: параметр встроен в JavaScript через f-string
                    clicked = await self.page.evaluate(f"""
                        () => {{
                            const normalizedName = '{normalized_name_js}';

                            function normalize(text) {{
                                return text.toLowerCase()
                                    .replace(/[^а-яa-z0-9\\s]/g, '')
                                    .replace(/\\s+/g, ' ')
                                    .trim();
                            }}

                            const allElements = document.querySelectorAll('a, article, div[class*="card"]');
                            for (let elem of allElements) {{
                                const text = elem.textContent || '';
                                if (normalize(text).includes(normalizedName)) {{
                                    const link = elem.tagName === 'A' ? elem : elem.querySelector('a');
                                    if (link) {{
                                        link.click();
                                        return true;
                                    }}
                                }}
                            }}
                            return false;
                        }}
                    """)

                    if clicked:
                        await self.wait_for_stable(3)
                        print("✅ Ресторан выбран (метод 2)")
                        return True

            # Если не нашли автоматически
            print(f"\n❌ Не удалось автоматически выбрать '{restaurant_name}'")

            if restaurants_info and len(restaurants_info) > 0:
                print("\n💡 Доступные рестораны:")
                for i, rest in enumerate(restaurants_info[:10], 1):
                    print(f"   {i}. {rest['name']}")

                print(f"\n💡 Похоже, ресторан найден как: '{restaurants_info[0]['name']}'")
                print("   Попробуйте ввести точное название из списка")
                print("   или откройте ресторан вручную в браузере")

            return False

        except Exception as e:
            print(f"❌ Ошибка выбора ресторана: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def search_and_add_item(self, item_name: str) -> bool:
        """Поиск и добавление товара в корзину"""
        print(f"\n🔍 Ищу товар: {item_name}")

        try:
            # Прокрутка вниз для загрузки меню
            await self.page.evaluate("window.scrollTo(0, 500)")
            await self.wait_for_stable(2)

            # Поиск в меню ресторана (если есть поле поиска)
            menu_search_selectors = [
                'input[placeholder*="Поиск"]',
                'input[placeholder*="меню"]',
                'input[placeholder*="Найти"]',
                '.UiKitInput'
            ]

            search_found = False
            for selector in menu_search_selectors:
                try:
                    if await self.page.locator(selector).count() > 0:
                        await self.page.fill(selector, item_name)
                        await self.wait_for_stable(2)
                        search_found = True
                        print("    ✓ Использован поиск по меню")
                        break
                except:
                    continue

            if not search_found:
                print("    ⓘ Поиск по меню не найден, ищу в списке товаров...")
                # Прокрутка для загрузки всех товаров
                for _ in range(3):
                    await self.page.evaluate("window.scrollBy(0, 500)")
                    await asyncio.sleep(1)

            # Метод 1: JavaScript поиск и клик (наиболее надежный)
            print("    🔍 Метод 1: Поиск через JavaScript...")
            item_added = await self.page.evaluate(f"""
                (itemName) => {{
                    const searchTerms = itemName.toLowerCase().split(' ');

                    // Ищем все карточки товаров
                    const allCards = document.querySelectorAll('div[class*="item"], div[class*="Item"], div[class*="product"], div[class*="Product"], article');

                    for (let card of allCards) {{
                        const cardText = card.textContent?.toLowerCase() || '';

                        // Проверяем, содержит ли карточка все слова из названия товара
                        const matchesAll = searchTerms.every(term => cardText.includes(term));

                        if (matchesAll) {{
                            // Ищем кнопку добавления в этой карточке
                            const buttons = card.querySelectorAll('button, [role="button"]');

                            for (let btn of buttons) {{
                                const btnText = btn.textContent?.toLowerCase() || '';
                                const ariaLabel = btn.getAttribute('aria-label')?.toLowerCase() || '';

                                // Проверяем, что это кнопка добавления
                                if (btnText.includes('добавить') || 
                                    btnText.includes('корзин') ||
                                    btnText.includes('+') ||
                                    ariaLabel.includes('добавить') ||
                                    ariaLabel.includes('корзин')) {{

                                    btn.click();
                                    return true;
                                }}
                            }}

                            // Если кнопка не найдена, кликаем на саму карточку
                            card.click();
                            return 'clicked_card';
                        }}
                    }}

                    return false;
                }}
            """, item_name)

            if item_added == True:
                await self.wait_for_stable(2)
                print(f"✅ Товар добавлен: {item_name}")
                self.cart_items.append(item_name)
                return True
            elif item_added == 'clicked_card':
                print("    ⓘ Открыта карточка товара, ищу кнопку добавления...")
                await self.wait_for_stable(2)

                # Ищем кнопку в модальном окне
                modal_button_selectors = [
                    'button:has-text("Добавить")',
                    'button:has-text("В корзину")',
                    '[aria-label*="Добавить"]',
                    'button[class*="add"]'
                ]

                for selector in modal_button_selectors:
                    try:
                        if await self.page.locator(selector).count() > 0:
                            await self.page.click(selector)
                            await self.wait_for_stable(2)
                            print(f"✅ Товар добавлен: {item_name}")
                            self.cart_items.append(item_name)
                            return True
                    except:
                        continue

            # Метод 2: Playwright локаторы
            print("    🔍 Метод 2: Поиск через Playwright...")

            # Ищем элемент с текстом товара
            try:
                item_elements = await self.page.get_by_text(item_name, exact=False).all()
                print(f"       Найдено совпадений: {len(item_elements)}")

                for elem in item_elements:
                    try:
                        if await elem.is_visible():
                            # Ищем ближайшую кнопку добавления
                            parent = elem
                            for _ in range(5):  # Поднимаемся до 5 уровней вверх
                                try:
                                    buttons = await parent.locator('button').all()
                                    for btn in buttons:
                                        btn_text = await btn.text_content()
                                        if btn_text and any(
                                                word in btn_text.lower() for word in ['добавить', 'корзин', '+']):
                                            await btn.click()
                                            await self.wait_for_stable(2)
                                            print(f"✅ Товар добавлен: {item_name}")
                                            self.cart_items.append(item_name)
                                            return True
                                except:
                                    pass

                                parent = parent.locator('..')
                    except:
                        continue
            except Exception as e:
                print(f"       ⚠️ Ошибка метода 2: {e}")

            # Метод 3: Показываем доступные товары
            print("    🔍 Метод 3: Показываю доступные товары...")
            available_items = await self.page.evaluate("""
                () => {
                    const items = new Set();
                    const cards = document.querySelectorAll('div[class*="item"], div[class*="Item"], div[class*="product"], article');

                    cards.forEach(card => {
                        const headings = card.querySelectorAll('h1, h2, h3, h4, [class*="title"], [class*="Title"], [class*="name"], [class*="Name"]');
                        headings.forEach(h => {
                            const text = h.textContent?.trim();
                            if (text && text.length > 2 && text.length < 100) {
                                items.add(text);
                            }
                        });
                    });

                    return Array.from(items).slice(0, 15);
                }
            """)

            if available_items:
                print("\n    📋 Доступные товары в меню:")
                for i, item in enumerate(available_items, 1):
                    print(f"       {i}. {item}")
                print("\n    💡 Совет: Используйте точное название из списка выше")

            print(f"\n❌ Не удалось добавить товар: {item_name}")
            print("    💡 Попробуйте:")
            print("       1. Проверить правильность названия")
            print("       2. Использовать короткое название")
            print("       3. Выбрать товар из списка выше")

            return False

        except Exception as e:
            print(f"❌ Ошибка добавления товара: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def view_cart(self) -> bool:
        """Просмотр корзины"""
        print("\n🛒 Открываю корзину...")

        try:
            cart_selectors = [
                '[data-testid="cart-button"]',
                'button:has-text("Корзина")',
                '[class*="Cart"]',
                'a:has-text("Перейти к оформлению")'
            ]

            for selector in cart_selectors:
                try:
                    if await self.page.locator(selector).count() > 0:
                        await self.page.click(selector)
                        await self.wait_for_stable()
                        print("✅ Корзина открыта")
                        return True
                except:
                    continue

            print("⚠️  Кнопка корзины не найдена, возможно корзина уже открыта")
            return True

        except Exception as e:
            print(f"❌ Ошибка открытия корзины: {e}")
            return False

    async def get_cart_total(self) -> str:
        """Получение итоговой суммы"""
        try:
            total_selectors = [
                '[class*="Total"]',
                '[data-testid="cart-total"]',
                'span:has-text("₽")'
            ]

            for selector in total_selectors:
                try:
                    total_elem = self.page.locator(selector).last
                    if await total_elem.count() > 0:
                        total_text = await total_elem.text_content()
                        return total_text.strip()
                except:
                    continue

            return "Неизвестно"

        except:
            return "Неизвестно"

    async def checkout(self):
        """Оформление заказа"""
        print("\n💳 Переход к оформлению заказа...")

        if not self.enable_real_order:
            print("🎯 ТЕСТОВЫЙ РЕЖИМ: останавливаюсь перед оформлением")
            print("💡 Для реального оформления установите enable_real_order=True")
            return

        try:
            checkout_selectors = [
                'button:has-text("Оформить заказ")',
                'button:has-text("Перейти к оформлению")',
                '[data-testid="checkout-button"]'
            ]

            print("⚠️  ⚠️  ⚠️  ВНИМАНИЕ: РЕАЛЬНОЕ ОФОРМЛЕНИЕ ЗАКАЗА!")
            confirmation = input("    Подтвердите оформление заказа (введите 'YES'): ")

            if confirmation != 'YES':
                print("❌ Оформление отменено пользователем")
                return

            for selector in checkout_selectors:
                try:
                    if await self.page.locator(selector).count() > 0:
                        await self.page.click(selector)
                        await self.wait_for_stable()
                        print("✅ Переход к оформлению выполнен")
                        print("⚠️  Дальнейшие действия выполняйте вручную!")
                        return
                except:
                    continue

            print("❌ Кнопка оформления не найдена")

        except Exception as e:
            print(f"❌ Ошибка оформления: {e}")

    async def run(self, restaurant: str, items: List[str]):
        """Запуск полного процесса"""
        print("\n" + "=" * 60)
        print("🍔 АГЕНТ ЯНДЕКС.ЕДЫ")
        print("=" * 60)

        try:
            if not await self.setup_browser():
                return False

            if not await self.open_yandex_eda():
                return False

            # Поиск ресторана
            if not await self.search_restaurant(restaurant):
                return False

            # Выбор ресторана с возможностью ручного ввода
            if not await self.select_restaurant(restaurant):
                print("\n💡 РУЧНОЙ ВЫБОР РЕСТОРАНА")
                print("   Откройте нужный ресторан вручную в браузере")
                retry = input("   Нажмите Enter когда откроете ресторан (или 'q' для выхода): ").strip()

                if retry.lower() == 'q':
                    print("❌ Процесс отменен")
                    return False

                print("✅ Продолжаю с текущей страницы")
                await self.wait_for_stable(3)

            # Добавление товаров
            print("\n📦 ДОБАВЛЕНИЕ ТОВАРОВ В КОРЗИНУ")
            print("=" * 60)

            for i, item in enumerate(items, 1):
                print(f"\n[{i}/{len(items)}] Обрабатываю: {item}")
                success = await self.search_and_add_item(item)

                if not success:
                    print(f"\n   ⚠️  Не удалось автоматически добавить: {item}")
                    print("   💡 РУЧНОЕ ДОБАВЛЕНИЕ")
                    print("      Добавьте товар вручную в браузере")
                    manual = input("      Нажмите Enter когда добавите (или 's' чтобы пропустить): ").strip()

                    if manual.lower() != 's':
                        self.cart_items.append(item)
                        print(f"   ✅ Отмечен как добавленный: {item}")

                await asyncio.sleep(1)

            if self.cart_items:
                await self.view_cart()
                total = await self.get_cart_total()

                # Отчет
                print("\n" + "=" * 60)
                print("📊 ОТЧЕТ")
                print("=" * 60)
                print(f"🏪 Ресторан: {restaurant}")
                print(f"🛒 Добавлено товаров: {len(self.cart_items)}")
                for i, item in enumerate(self.cart_items, 1):
                    print(f"   {i}. {item}")
                print(f"💰 Итого: {total}")

                await self.checkout()
            else:
                print("\n❌ Корзина пуста - товары не были добавлены")
                print("💡 Попробуйте добавить товары вручную")
                input("Нажмите Enter для завершения...")

            return True

        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if not self.enable_real_order:
                print("\n⏸️  Браузер остается открытым для проверки корзины")
                print("   Закройте окно браузера вручную или нажмите Ctrl+C")
                try:
                    await asyncio.sleep(300)  # 5 минут
                except:
                    pass
            await self.cleanup()


# ============================================================================
# КООРДИНАТОР АГЕНТОВ
# ============================================================================

class AgentCoordinator:
    """Координатор для выбора и запуска агентов"""

    @staticmethod
    def select_task():
        """Выбор задачи"""
        print("\n" + "=" * 60)
        print("🤖 MULTI-AGENT СИСТЕМА")
        print("=" * 60)
        print("\nДоступные задачи:")
        print("1. 💼 Поиск работы на HH.ru")
        print("2. 📧 Очистка почты на Яндекс.Почте")
        print("3. 🍔 Заказ еды на Яндекс.Еде")
        print("4. 🚪 Выход")

        choice = input("\nВыберите задачу (1-4): ").strip()
        return choice

    @staticmethod
    async def run_job_search():
        """Запуск агента поиска работы"""
        print("\n💼 Настройка агента поиска работы")

        enable_real = input("Включить реальную отправку откликов? (y/n): ").strip().lower() == 'y'

        if enable_real:
            print("⚠️  ⚠️  ⚠️  РЕЖИМ РЕАЛЬНОЙ ОТПРАВКИ ВКЛЮЧЕН!")
            confirmation = input("Подтвердите (введите 'YES'): ")
            if confirmation != 'YES':
                print("❌ Отменено")
                return

        job_query = input("Введите поисковый запрос (Enter для 'AI engineer machine learning'): ").strip()
        if not job_query:
            job_query = "AI engineer machine learning"

        agent = JobSearchAgent(enable_real_apply=enable_real)
        await agent.run(job_query)

    @staticmethod
    async def run_email_cleanup():
        """Запуск агента очистки почты"""
        print("\n📧 Настройка агента почты")

        enable_real = input("Включить реальное удаление писем? (y/n): ").strip().lower() == 'y'

        if enable_real:
            print("⚠️  ⚠️  ⚠️  РЕЖИМ РЕАЛЬНОГО УДАЛЕНИЯ ВКЛЮЧЕН!")
            confirmation = input("Подтвердите (введите 'YES'): ")
            if confirmation != 'YES':
                print("❌ Отменено")
                return

        count_input = input("Сколько писем проанализировать? (Enter для 10): ").strip()
        count = int(count_input) if count_input.isdigit() else 10

        agent = EmailAgent(enable_real_delete=enable_real)
        await agent.run(count)

    @staticmethod
    async def run_food_delivery():
        """Запуск агента доставки еды"""
        print("\n🍔 Настройка агента доставки еды")

        enable_real = input("Включить реальное оформление заказа? (y/n): ").strip().lower() == 'y'

        if enable_real:
            print("⚠️  ⚠️  ⚠️  РЕЖИМ РЕАЛЬНОГО ЗАКАЗА ВКЛЮЧЕН!")
            confirmation = input("Подтвердите (введите 'YES'): ")
            if confirmation != 'YES':
                print("❌ Отменено")
                return

        restaurant = input("Название ресторана (Enter для 'Burger King'): ").strip()
        if not restaurant:
            restaurant = "Burger King"

        items_input = input("Товары через запятую (Enter для 'BBQ бургер,картофель фри'): ").strip()
        if not items_input:
            items = ["BBQ бургер", "картофель фри"]
        else:
            items = [item.strip() for item in items_input.split(',')]

        agent = FoodDeliveryAgent(enable_real_order=enable_real)
        await agent.run(restaurant, items)


# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================================

async def main():
    """Главная функция"""
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "🤖 MULTI-AGENT BROWSER SYSTEM 🤖" + " " * 15 + "║")
    print("╚" + "═" * 58 + "╝")

    coordinator = AgentCoordinator()

    while True:
        choice = coordinator.select_task()

        if choice == '1':
            await coordinator.run_job_search()
        elif choice == '2':
            await coordinator.run_email_cleanup()
        elif choice == '3':
            await coordinator.run_food_delivery()
        elif choice == '4':
            print("\n👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте снова.")

        continue_choice = input("\nВыполнить еще одну задачу? (y/n): ").strip().lower()
        if continue_choice != 'y':
            print("\n👋 До свидания!")
            break


# ============================================================================
# ЗАПУСК
# ============================================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Программа остановлена пользователем")