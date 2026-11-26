"""Bilingual content for the XLANORA site (English and Arabic).

Single source of truth for all visible text, services and photos.
build/build.py turns this into static HTML under site/en/ and site/ar/.
"""

BRAND = "XLANORA"
CONTACT_EMAIL = "contactxlanora@gmail.com"
PAYPAL_EMAIL = "mo.t.hassan001@gmail.com"

# Services offered (from the original brief: photography, home maintenance, education).
# Each service opens its own detail page. Slugs are used in URLs and in the database.
SERVICES = [
    {
        "slug": "photography",
        "image": "photographer-interior",
        "alt": {
            "en": "Photographer shooting an interior with a DSLR camera",
            "ar": "مصور يلتقط صورة لمساحة داخلية بكاميرا احترافية",
        },
        "title": {"en": "Photography", "ar": "التصوير الفوتوغرافي"},
        "short": {
            "en": "Professional photography for homes, interiors and projects.",
            "ar": "تصوير احترافي للمنازل والمساحات الداخلية والمشاريع.",
        },
        "body": {
            "en": "Our photographers capture spaces in clear, flattering light. Ideal for property listings, interior projects and portfolios.",
            "ar": "يلتقط مصورونا المساحات بإضاءة واضحة ومتقنة. مثالي لإعلانات العقارات ومشاريع الديكور والمعارض الشخصية.",
        },
        "points": {
            "en": ["Interior and exterior shoots", "Editing and colour correction", "Delivery in web and print sizes"],
            "ar": ["تصوير داخلي وخارجي", "معالجة الصور وتصحيح الألوان", "تسليم بمقاسات للويب والطباعة"],
        },
    },
    {
        "slug": "home-maintenance",
        "image": "ac-technician",
        "alt": {
            "en": "Technician servicing a wall-mounted air conditioner",
            "ar": "فني يصون مكيفاً مثبتاً على الحائط",
        },
        "title": {"en": "Home Maintenance", "ar": "صيانة المنازل"},
        "short": {
            "en": "Repairs, installations and smart-home setup by trained technicians.",
            "ar": "إصلاحات وتركيبات وإعداد المنزل الذكي على يد فنيين مدربين.",
        },
        "body": {
            "en": "From air conditioning service to smart-home devices, our technicians keep your home running smoothly.",
            "ar": "من صيانة التكييف إلى أجهزة المنزل الذكي، يحافظ فنيونا على سلاسة عمل منزلك.",
        },
        "points": {
            "en": ["Air conditioning service and repair", "Smart-home installation", "Electrical and general repairs"],
            "ar": ["صيانة التكييف وإصلاحه", "تركيب أنظمة المنزل الذكي", "إصلاحات كهربائية وعامة"],
        },
        "extra_image": "smart-home-technician",
        "extra_alt": {
            "en": "Technician showing a smart-home control app on a tablet",
            "ar": "فني يعرض تطبيق التحكم في المنزل الذكي على جهاز لوحي",
        },
    },
    {
        "slug": "education-training",
        "image": "education-tutor",
        "alt": {
            "en": "Tutor helping a student at a table with a tablet and books",
            "ar": "مدرس يساعد طالباً على طاولة بها جهاز لوحي وكتب",
        },
        "title": {"en": "Education & Training", "ar": "التعليم والتدريب"},
        "short": {
            "en": "Tutoring and training with experienced instructors.",
            "ar": "دروس خصوصية وتدريب على يد مدربين ذوي خبرة.",
        },
        "body": {
            "en": "One-to-one tutoring and group training with instructors who make hard subjects clear and practical.",
            "ar": "دروس فردية وتدريب جماعي مع مدربين يجعلون المواد الصعبة واضحة وعملية.",
        },
        "points": {
            "en": ["One-to-one tutoring", "Group training sessions", "Study plans and progress reviews"],
            "ar": ["دروس فردية", "جلسات تدريب جماعية", "خطط دراسية ومراجعة للتقدم"],
        },
    },
    {
        "slug": "graphic-design",
        "image": "graphic-design",
        "alt": {
            "en": "XLANORA brand graphic for graphic design services",
            "ar": "تصميم بهوية XLANORA لخدمات التصميم الجرافيكي",
        },
        "title": {"en": "Graphic Design", "ar": "التصميم الجرافيكي"},
        "short": {
            "en": "Logos, brand identity, posters and social visuals that look professional.",
            "ar": "شعارات وهويات بصرية وملصقات وتصاميم للتواصل تبدو احترافية.",
        },
        "body": {
            "en": "Clear, memorable designs that tell your story. From a first logo to a full brand kit, we design for print and screens.",
            "ar": "تصاميم واضحة وجذابة تحكي قصتك. من أول شعار إلى دليل هوية كامل، نصمم للطباعة والشاشات.",
        },
        "points": {
            "en": ["Logo and brand identity", "Posters, flyers and print material", "Social media visuals"],
            "ar": ["تصميم الشعار والهوية البصرية", "ملصقات ونشرات ومواد مطبوعة", "تصاميم لمنصات التواصل"],
        },
    },
    {
        "slug": "web-development",
        "image": "web-development",
        "alt": {
            "en": "Developer coding on a laptop beside a glowing code cube",
            "ar": "مطور يكتب الشيفرة على حاسوب محمول بجانب مكعب برمجي مضيء",
        },
        "title": {"en": "Web Development", "ar": "تطوير المواقع"},
        "short": {
            "en": "Fast, responsive websites and web apps built to turn visitors into customers.",
            "ar": "مواقع وتطبيقات ويب سريعة ومتجاوبة مصممة لتحويل الزوار إلى عملاء.",
        },
        "body": {
            "en": "We build clean, secure websites that load fast on phones and desktops, in Arabic and English.",
            "ar": "نبني مواقع نظيفة وآمنة تعمل بسرعة على الجوال والحاسوب، وتدعم العربية والإنجليزية.",
        },
        "points": {
            "en": ["Business and landing websites", "Online booking and contact forms", "Hosting setup and maintenance"],
            "ar": ["مواقع الشركات وصفحات الهبوط", "الحجز الإلكتروني ونماذج التواصل", "إعداد الاستضافة والصيانة"],
        },
    },
    {
        "slug": "video-editing",
        "image": "video-editing",
        "alt": {
            "en": "Editor working on a video timeline on a large monitor, wearing headphones",
            "ar": "محرر يعمل على خط زمني لفيديو على شاشة كبيرة وهو يرتدي سماعات",
        },
        "title": {"en": "Video Editing", "ar": "مونتاج الفيديو"},
        "short": {
            "en": "Edited videos for ads, social media and presentations.",
            "ar": "مونتاج احترافي لإعلانات وفيديوهات التواصل والعروض التقديمية.",
        },
        "body": {
            "en": "Cutting, colour grading, sound and motion graphics, turned into short clips or longer films that hold attention.",
            "ar": "قص وتصحيح ألوان وصوت ورسوم متحركة، لتتحول مادتك إلى مقاطع قصيرة أو أفلام تشد الانتباه.",
        },
        "points": {
            "en": ["Short clips for social media", "Ads and promotional videos", "Colour grading and sound clean-up"],
            "ar": ["مقاطع قصيرة لمنصات التواصل", "إعلانات وفيديوهات ترويجية", "تصحيح الألوان وتنظيف الصوت"],
        },
    },
    {
        "slug": "digital-marketing",
        "image": "digital-marketing",
        "alt": {
            "en": "Laptop showing a growth chart beside a mug and a phone",
            "ar": "حاسوب محمول يعرض مخطط نمو بجانب كوب وهاتف",
        },
        "title": {"en": "Digital Marketing", "ar": "التسويق الرقمي"},
        "short": {
            "en": "Campaigns that bring measurable growth to your business.",
            "ar": "حملات تحقق نمواً قابلاً للقياس لعملك.",
        },
        "body": {
            "en": "We plan, run and measure online campaigns and paid ads, so every riyal is tracked and improved.",
            "ar": "نخطط ونُدير ونقيس الحملات الإلكترونية والإعلانات المدفوعة، فكل ريال يُتابَع ويُحسَّن.",
        },
        "points": {
            "en": ["Campaign planning and budgets", "Search and paid advertising", "Monthly performance reports"],
            "ar": ["تخطيط الحملات والميزانيات", "الإعلانات المدفوعة وظهور البحث", "تقارير أداء شهرية"],
        },
    },
    {
        "slug": "translation-services",
        "image": "translation-services",
        "alt": {
            "en": "A globe, a dictionary and language tiles on a desk",
            "ar": "كرة أرضية وقاموس ومكعبات لغات على مكتب",
        },
        "title": {"en": "Translation Services", "ar": "خدمات الترجمة"},
        "short": {
            "en": "Accurate translation between Arabic, English and more.",
            "ar": "ترجمة دقيقة بين العربية والإنجليزية ولغات أخرى.",
        },
        "body": {
            "en": "Professional translators for documents, websites and marketing content, with careful review so the meaning stays exact.",
            "ar": "مترجمون محترفون للوثائق والمواقع والمحتوى التسويقي، مع مراجعة دقيقة تحافظ على المعنى.",
        },
        "points": {
            "en": ["Documents and certificates", "Website and marketing content", "Proofreading and review"],
            "ar": ["الوثائق والشهادات", "محتوى المواقع والتسويق", "التدقيق اللغوي والمراجعة"],
        },
    },
    {
        "slug": "social-media-management",
        "image": "social-media-management",
        "alt": {
            "en": "Phone showing social media app icons with like and follower bubbles",
            "ar": "هاتف يعرض تطبيقات التواصل مع فقاعات الإعجاب والمتابعين",
        },
        "title": {"en": "Social Media Management", "ar": "إدارة وسائل التواصل الاجتماعي"},
        "short": {
            "en": "We plan, create and publish content, and grow your audience.",
            "ar": "نخطط للمحتوى وننشئه وننشره وننمّي جمهورك.",
        },
        "body": {
            "en": "A monthly plan of posts, stories and replies, with a posting calendar, branded visuals and clear reports.",
            "ar": "خطة شهرية للمنشورات والقصص والردود، مع تقويم للنشر وتصاميم بهوية علامتك التجارية وتقارير واضحة.",
        },
        "points": {
            "en": ["Content calendar and posting", "Replies and community management", "Growth and engagement reports"],
            "ar": ["تقويم المحتوى والنشر", "الردود وإدارة المجتمع", "تقارير النمو والتفاعل"],
        },
    },
]

SERVICE_BY_SLUG = {s["slug"]: s for s in SERVICES}

# Photos used on the About page (team-style gallery). Alt text is generic on purpose.


TEXT = {
    "en": {
        "lang_name": "English",
        "other_lang": "العربية",
        "other_href_prefix": "/ar",
        "nav_home": "Home",
        "nav_services": "Services",
        "nav_about": "About",
        "nav_contact": "Contact",
        "nav_menu": "Menu",
        "cta_quote": "Request a quote",
        "lang_label": "Language",
        "skip": "Skip to content",
        "hero_title": "Find the Right Freelancer. Get Your Work Done.",
        "hero_lead": "Discover talented freelancers, explore their portfolios, compare services, and work together in one simple platform.",
        "hero_become": "Become a Freelancer",
        "hero_explore": "Explore Services",
        "footer_paypal": "Support XLANORA via PayPal:",
        "hero_cta": "Find a Freelancer",
        "home_services_title": "What we offer",
        "home_services_lead": "Nine services, one simple way to book.",
        "view_service": "View service",
        "why_title": "Why XLANORA",
        "why_points": [
            ("Clear process", "Tell us what you need and we reply with a quote."),
            ("Independent freelancers", "Each freelancer sets their own services, prices and portfolio."),
            ("Simple contact", "Reach us by form or email, in English or Arabic."),
        ],
        "services_title": "Freelancers",
        "services_lead": "Browse freelancers, compare services and prices, then open a profile to request a quote.",
        "services_collage_alt": "Six XLANORA services: graphic design, web development, video editing, digital marketing, translation and social media",
        "detail_included": "What is included",
        "detail_request": "Request a quote for this service",
        "back_services": "Back to all services",
        "about_title": "About XLANORA",
        "about_lead": "XLANORA is a marketplace that connects clients with independent freelancers. Good work should be easy to find, easy to book and easy to trust.",
        "about_story_title": "How XLANORA works",
        "about_story": "Clients search for a service, compare freelancers and their portfolios, and send a booking request. The freelancer accepts, you agree on the price and delivery time, and you work together directly.",
        "about_direct": "XLANORA does not hold, collect or transfer client money. Agree on a payment method with your freelancer outside the platform.",
        "about_team_title": "Direct payments",
        "about_values_title": "Important to know",
        "about_values": [
            "XLANORA connects clients with independent freelancers. Payments are arranged directly between clients and freelancers. XLANORA does not charge service commissions or process payments.",
            "Agree on the price and the delivery time before starting, and confirm the requirements in writing.",
            "Keep copies of agreements and receipts. Be careful with unknown payment links and unexpected advance fees.",
        ],
        "contact_title": "Contact us",
        "contact_lead": "Tell us what you need. We reply by email as soon as we can.",
        "contact_email_label": "Email",
        "form_name": "Full name",
        "form_email": "Email address",
        "form_phone": "Phone (optional)",
        "form_service": "Service",
        "form_service_choose": "Choose a service",
        "form_service_unsure": "Not sure yet",
        "form_message": "Your message",
        "form_submit": "Send request",
        "form_sending": "Sending...",
        "form_success": "Thank you. Your request has been received. We will reply by email.",
        "form_error_network": "We could not send your request. Please try again or email us directly.",
        "form_error_generic": "Please check the highlighted fields.",
        "err_name": "Please enter your name (2 to 80 characters).",
        "err_email": "Please enter a valid email address.",
        "err_phone": "Phone may only contain digits, spaces, + - ( ).",
        "err_service": "Please choose a service from the list.",
        "err_message": "Please write a message (10 to 2000 characters).",
        "footer_tag": "Connecting you with trusted professionals.",
        "footer_rights": "All rights reserved.",
        "footer_contact": "Contact",
        "mobile_menu_open": "Open menu",
        "mobile_menu_close": "Close menu",
    },
    "ar": {
        "lang_name": "العربية",
        "other_lang": "English",
        "other_href_prefix": "/en",
        "nav_home": "الرئيسية",
        "nav_services": "الخدمات",
        "nav_about": "من نحن",
        "nav_contact": "تواصل معنا",
        "nav_menu": "القائمة",
        "cta_quote": "اطلب عرض سعر",
        "lang_label": "اللغة",
        "skip": "انتقل إلى المحتوى",
        "hero_title": "اعثر على المستقل المناسب. أنجز عملك.",
        "hero_lead": "اكتشف مستقلين موهوبين، وتصفح أعمالهم، وقارن الخدمات، واعملوا معاً في منصة واحدة بسيطة.",
        "hero_become": "كن مستقلاً",
        "hero_explore": "استكشف الخدمات",
        "footer_paypal": "ادعم XLANORA عبر PayPal:",
        "hero_cta": "ابحث عن مستقل",
        "home_services_title": "ما نقدمه",
        "home_services_lead": "تسع خدمات، وطريقة واحدة بسيطة للحجز.",
        "view_service": "عرض الخدمة",
        "why_title": "لماذا XLANORA",
        "why_points": [
            ("خطوات واضحة", "أخبرنا بما تحتاجه، ونرد عليك بعرض سعر."),
            ("مستقلون", "كل مستقل يحدد خدماته وأسعاره وأعماله بنفسه."),
            ("تواصل بسيط", "تواصل معنا عبر النموذج أو البريد الإلكتروني، بالعربية أو الإنجليزية."),
        ],
        "services_title": "المستقلون",
        "services_lead": "تصفح المستقلين، وقارن الخدمات والأسعار، ثم افتح الملف لطلب عرض سعر.",
        "services_collage_alt": "ستة من خدمات XLANORA: التصميم الجرافيكي وتطوير المواقع ومونتاج الفيديو والتسويق الرقمي والترجمة والتواصل الاجتماعي",
        "detail_included": "ما الذي تشمله الخدمة",
        "detail_request": "اطلب عرض سعر لهذه الخدمة",
        "back_services": "العودة إلى كل الخدمات",
        "about_title": "عن XLANORA",
        "about_lead": "XLANORA منصة تربط العملاء بمستقلين مستقلين. يجب أن يكون العمل الجيد سهل الوصول إليه وسهل الحجز وجديراً بالثقة.",
        "about_story_title": "كيف تعمل XLANORA",
        "about_story": "يبحث العميل عن خدمة، ويقارن المستقلين وأعمالهم، ثم يرسل طلب حجز. يقبل المستقل العمل، ويتفق الطرفان على السعر ومدة التسليم، ثم يعملان معاً مباشرة.",
        "about_direct": "لا تحتفظ XLANORA بأموال العملاء ولا تحصلها ولا تحولها. اتفق مع المستقل على طريقة الدفع خارج المنصة.",
        "about_team_title": "الدفع المباشر",
        "about_values_title": "معلومات مهمة",
        "about_values": [
            "تربط XLANORA العملاء بمستقلين مستقلين. يتم الدفع مباشرة بين العميل والمستقل. لا تفرض XLANORA عمولة على الخدمات ولا تعالج المدفوعات.",
            "اتفقا على السعر ومدة التسليم قبل البدء، وأكدا المتطلبات كتابةً.",
            "احتفظ بنسخ من الاتفاقات والإيصالات. احذر من روابط الدفع غير المعروفة ومن الرسوم المقدمة غير المتوقعة.",
        ],
        "contact_title": "تواصل معنا",
        "contact_lead": "أخبرنا بما تحتاجه. نرد عليك عبر البريد الإلكتروني في أقرب وقت.",
        "contact_email_label": "البريد الإلكتروني",
        "form_name": "الاسم الكامل",
        "form_email": "البريد الإلكتروني",
        "form_phone": "رقم الهاتف (اختياري)",
        "form_service": "الخدمة",
        "form_service_choose": "اختر خدمة",
        "form_service_unsure": "لم أحسم بعد",
        "form_message": "رسالتك",
        "form_submit": "إرسال الطلب",
        "form_sending": "جارٍ الإرسال...",
        "form_success": "شكراً لك. تم استلام طلبك، وسنرد عليك عبر البريد الإلكتروني.",
        "form_error_network": "تعذر إرسال طلبك. حاول مرة أخرى، أو راسلنا مباشرة عبر البريد.",
        "form_error_generic": "يرجى مراجعة الحقول المعلَّمة.",
        "err_name": "يرجى إدخال اسمك (من 2 إلى 80 حرفاً).",
        "err_email": "يرجى إدخال بريد إلكتروني صحيح.",
        "err_phone": "يجب أن يحتوي الهاتف على أرقام ومسافات و + - ( ) فقط.",
        "err_service": "يرجى اختيار خدمة من القائمة.",
        "err_message": "يرجى كتابة رسالة (من 10 إلى 2000 حرف).",
        "footer_tag": "نربطك بمحترفين موثوقين.",
        "footer_rights": "جميع الحقوق محفوظة.",
        "footer_contact": "تواصل",
        "mobile_menu_open": "فتح القائمة",
        "mobile_menu_close": "إغلاق القائمة",
    },
}
