# თარო — ონლაინ მაღაზია (Django + EverREST)

Django აპლიკაცია [EverREST API](https://everrest.educata.dev)-ზე.

- ნივთები და მათი სურათები API-დან ჩამოიტვირთება ბრძანებით `import_products`
  და ინახება Django-ს ბაზაში (`Product`) და `media/` საქაღალდეში. კატალოგი,
  ძებნა და ფილტრი მუშაობს ამ ასლზე.
- ავტორიზაცია, კალათა და რეიტინგი პირდაპირ API-ზე სრულდება.
- ტექსტური შეფასებები (სახელი გვარი, ვარსკვლავები, ტექსტი) ინახება Django-ს
  ბაზაში (`Review`).

`import_products` შეიძლება ხელახლა გაეშვას ფასებისა და მარაგის გასაახლებლად.

## გაშვება

```
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py import_products
.venv\Scripts\python manage.py runserver
```

გახსენით http://127.0.0.1:8000

ტესტები: `.venv\Scripts\python manage.py test`

## ადმინ პანელი

მისამართი: http://127.0.0.1:8000/admin/ — ადმინისტრატორის შესაქმნელად:

```
.venv\Scripts\python manage.py createsuperuser
```

- **ნივთები:** ძებნა, ფილტრი (კატეგორია, ბრენდი, მარაგი, ფოტო), რედაქტირება,
  საკუთარი ფოტოს ატვირთვა და არჩეული ნივთების განახლება API-დან.
- **შეფასებები:** ნახვა, რედაქტირება, წაშლა.

ნივთი, რომელსაც არც ერთი ფოტო არ აქვს, მაღაზიაში არ ჩანს; ადმინ პანელიდან
ფოტოს ატვირთვის შემდეგ ის ავტომატურად გამოჩნდება.

## სტრუქტურა

| ფაილი | დანიშნულება |
| --- | --- |
| `shop/everrest.py` | EverREST API-ის კლიენტი (ძებნა, ავტორიზაცია, კალათა, რეიტინგი) |
| `shop/views.py` | გვერდები: მთავარი, ნივთი, კალათა, შესვლა, რეგისტრაცია |
| `shop/models.py` | `Product` — ნივთის ლოკალური ასლი, `Review` — ტექსტური შეფასება |
| `shop/management/commands/import_products.py` | ნივთებისა და სურათების ჩამოტვირთვა API-დან |
| `shop/templates/shop/` | HTML შაბლონები |
| `shop/static/shop/` | CSS და JavaScript |

მომხმარებლის `access_token` და `refresh_token` ინახება Django-ს სესიაში,
ბრაუზერს ისინი არ გადაეცემა.
